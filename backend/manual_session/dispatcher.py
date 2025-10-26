from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Optional, cast

from backend.codex_client import (
    EventDispatcher,
    EventKind,
    ItemEvent,
    ItemType,
    ProcessFinishedEvent,
    ProcessStartedEvent,
    RunnerCommandEvent,
    TextStreamEvent,
    ThreadStartedEvent,
    TurnCompletedEvent,
    TurnFailedEvent,
    CodexEvent,
)

from .models import ChatMessage, SessionRecord


@dataclass
class SessionEvent:
    session_id: str


@dataclass
class SessionMessageEvent(SessionEvent):
    message: ChatMessage


@dataclass
class SessionTokenEvent(SessionEvent):
    usage: Dict[str, object]


@dataclass
class SessionLifecycleEvent(SessionEvent):
    reason: str
    returncode: Optional[int] = None


SessionEventCallback = Callable[[SessionEvent], Awaitable[None]]


class ManualSessionEventAdapter:
    """
    Map Codex CLI events to higher-level session events.
    """

    def __init__(
        self,
        session: SessionRecord,
        emit: SessionEventCallback,
        process_holder: Optional[list] = None,
    ) -> None:
        self.session = session
        self.emit = emit
        self.process_holder = process_holder or []

    def build_dispatcher(self) -> EventDispatcher:
        async def handle_runner_command(event: RunnerCommandEvent) -> None:
            cmd = " ".join(event.command)
            message = self.session.append_system(
                f"$ {cmd}",
                kind="command_context",
            )
            await self.emit(SessionMessageEvent(self.session.id, message))

        async def handle_process_started(event: ProcessStartedEvent) -> None:
            async with self.session.lock:
                if self.process_holder:
                    self.session.active_process = self.process_holder[0]

        async def handle_process_finished(event: ProcessFinishedEvent) -> None:
            async with self.session.lock:
                self.session.active_process = None
            if event.returncode:
                message = self.session.append_system(
                    f"Codex 退出状态 {event.returncode}",
                    kind="command_complete",
                )
                await self.emit(SessionMessageEvent(self.session.id, message))
            await self.emit(
                SessionLifecycleEvent(
                    session_id=self.session.id,
                    reason="process_finished",
                    returncode=event.returncode,
                )
            )

        async def handle_stdout(event: TextStreamEvent) -> None:
            if event.text.strip() == "Reading prompt from stdin...":
                return
            message = self.session.append_codex_output(
                f"{event.text}\n",
                is_error=False,
                kind="stdout",
            )
            await self.emit(SessionMessageEvent(self.session.id, message))

        async def handle_stderr(event: TextStreamEvent) -> None:
            if event.text.strip() == "Reading prompt from stdin...":
                return
            message = self.session.append_codex_output(
                f"[stderr] {event.text}\n",
                is_error=True,
                kind="stderr",
            )
            await self.emit(SessionMessageEvent(self.session.id, message))

        async def handle_thread_started(event: ThreadStartedEvent) -> None:
            self.session.thread_id = event.thread_id or self.session.thread_id
            await self.emit(
                SessionLifecycleEvent(
                    session_id=self.session.id,
                    reason="thread_started",
                    returncode=None,
                )
            )

        async def handle_agent_message(event: ItemEvent) -> None:
            text = (event.payload or {}).get("text") or ""
            if not text:
                return
            if not text.endswith("\n"):
                text += "\n"
            message = self.session.append_codex_output(
                text,
                is_error=False,
                kind="agent_message",
            )
            await self.emit(SessionMessageEvent(self.session.id, message))

        async def handle_reasoning(event: ItemEvent) -> None:
            text = (event.payload or {}).get("text")
            if not text:
                return
            message = self.session.append_codex_output(
                f"{text}\n",
                is_error=False,
                kind="reasoning",
            )
            await self.emit(SessionMessageEvent(self.session.id, message))

        async def handle_command(event: ItemEvent) -> None:
            payload = event.payload or {}
            command = payload.get("command", "")
            output = payload.get("aggregated_output", "") or ""
            exit_code = payload.get("exit_code")
            status = (payload.get("status") or "").lower()

            if event.kind == EventKind.ITEM_STARTED:
                return
            elif event.kind == EventKind.ITEM_UPDATED:
                if not output:
                    return
                message = self.session.append_codex_output(
                    f"{output}",
                    is_error=False,
                    kind="command_execution",
                )
            else:
                details = f"$ {command}\n{output}"
                if exit_code is not None:
                    details += f"\n[退出码 {exit_code}]"
                if status and status not in {"completed", "success"}:
                    details += f"\n状态：{status}"
                message = self.session.append_codex_output(
                    f"{details}\n",
                    is_error=exit_code not in (0, None),
                    kind="command_execution",
                )
            await self.emit(SessionMessageEvent(self.session.id, message))

        async def handle_error_item(event: ItemEvent) -> None:
            text = (event.payload or {}).get("text") or "未知错误"
            message = self.session.append_codex_output(
                f"{text}\n",
                is_error=True,
                kind="error",
            )
            await self.emit(SessionMessageEvent(self.session.id, message))

        async def handle_generic_item(event: ItemEvent) -> None:
            payload = event.payload or {}
            item_type = event.item_type
            if item_type == ItemType.FILE_CHANGE:
                changes = payload.get("changes") or []
                if not changes:
                    return
                lines = [
                    f"{change.get('kind', 'update')}: {change.get('path', '-')}"
                    for change in changes
                ]
                message = self.session.append_codex_output(
                    "\n".join(lines) + "\n",
                    is_error=False,
                    kind="file_change",
                )
                await self.emit(SessionMessageEvent(self.session.id, message))
            elif item_type == ItemType.MCP_TOOL_CALL:
                tool = payload.get("tool") or payload.get("server") or ""
                status = payload.get("status") or ""
                message = self.session.append_codex_output(
                    f"{tool} 状态：{status or '进行中'}\n",
                    is_error=False,
                    kind="mcp_tool",
                )
                await self.emit(SessionMessageEvent(self.session.id, message))
            elif item_type == ItemType.WEB_SEARCH:
                query = payload.get("query") or ""
                message = self.session.append_codex_output(
                    f"{query}\n",
                    is_error=False,
                    kind="web_search",
                )
                await self.emit(SessionMessageEvent(self.session.id, message))
            elif item_type == ItemType.TODO_LIST:
                items = payload.get("items") or []
                if not items:
                    return
                lines = [
                    f"{'[x]' if item.get('completed') else '[ ]'} {item.get('text', '')}"
                    for item in items
                ]
                message = self.session.append_codex_output(
                    "\n".join(lines) + "\n",
                    is_error=False,
                    kind="todo_list",
                )
                await self.emit(SessionMessageEvent(self.session.id, message))

        async def handle_turn_completed(event: TurnCompletedEvent) -> None:
            usage = event.usage
            raw_input = usage.input_tokens
            cached_input = usage.cached_input_tokens
            output_tokens = usage.output_tokens
            reasoning_tokens = usage.reasoning_output_tokens
            effective_input = max(raw_input - cached_input, 0)
            total_tokens = usage.total_tokens or (
                effective_input + output_tokens + reasoning_tokens
            )
            last = {
                "input_tokens": effective_input,
                "cached_input_tokens": cached_input,
                "output_tokens": output_tokens,
                "reasoning_output_tokens": reasoning_tokens,
                "raw_input_tokens": raw_input,
                "total_tokens": total_tokens,
            }
            prev_total_raw: Dict[str, int] = {}
            if isinstance(self.session.token_usage, dict):
                total_field = self.session.token_usage.get("total")
                if isinstance(total_field, dict):
                    prev_total_raw = {
                        k: int(v)
                        for k, v in total_field.items()
                        if isinstance(v, (int, float))
                    }
            total: Dict[str, int] = {}
            for key, value in last.items():
                if value is None:
                    continue
                total[key] = int(prev_total_raw.get(key, 0)) + int(value)
            self.session.token_usage = {
                "total": total,
                "last": last,
                "timestamp": dt.datetime.utcnow().isoformat(),
            }
            await self.emit(
                SessionTokenEvent(
                    session_id=self.session.id,
                    usage=self.session.token_usage,
                )
            )

        async def handle_turn_failed(event: TurnFailedEvent) -> None:
            message = self.session.append_codex_output(
                f"{event.message}\n",
                is_error=True,
                kind="error",
            )
            await self.emit(SessionMessageEvent(self.session.id, message))

        async def noop(_: CodexEvent) -> None:
            return

        handlers: Dict[EventKind, Callable[[CodexEvent], Awaitable[None]]] = {
            EventKind.RUNNER_COMMAND: cast(
                Callable[[CodexEvent], Awaitable[None]], handle_runner_command
            ),
            EventKind.PROCESS_STARTED: cast(
                Callable[[CodexEvent], Awaitable[None]], handle_process_started
            ),
            EventKind.PROCESS_FINISHED: cast(
                Callable[[CodexEvent], Awaitable[None]], handle_process_finished
            ),
            EventKind.STDOUT_NON_JSON: cast(
                Callable[[CodexEvent], Awaitable[None]], handle_stdout
            ),
            EventKind.STDERR_LINE: cast(
                Callable[[CodexEvent], Awaitable[None]], handle_stderr
            ),
            EventKind.THREAD_STARTED: cast(
                Callable[[CodexEvent], Awaitable[None]], handle_thread_started
            ),
            EventKind.TURN_STARTED: cast(
                Callable[[CodexEvent], Awaitable[None]], noop
            ),
            EventKind.TURN_COMPLETED: cast(
                Callable[[CodexEvent], Awaitable[None]], handle_turn_completed
            ),
            EventKind.TURN_FAILED: cast(
                Callable[[CodexEvent], Awaitable[None]], handle_turn_failed
            ),
            EventKind.STREAM_ERROR: cast(
                Callable[[CodexEvent], Awaitable[None]], handle_turn_failed
            ),
            EventKind.ITEM_STARTED: cast(
                Callable[[CodexEvent], Awaitable[None]], handle_generic_item
            ),
            EventKind.ITEM_UPDATED: cast(
                Callable[[CodexEvent], Awaitable[None]], handle_generic_item
            ),
            EventKind.ITEM_COMPLETED: cast(
                Callable[[CodexEvent], Awaitable[None]], handle_generic_item
            ),
        }
        item_handlers = {
            ItemType.AGENT_MESSAGE: cast(
                Callable[[ItemEvent], Awaitable[None]], handle_agent_message
            ),
            ItemType.REASONING: cast(
                Callable[[ItemEvent], Awaitable[None]], handle_reasoning
            ),
            ItemType.COMMAND_EXECUTION: cast(
                Callable[[ItemEvent], Awaitable[None]], handle_command
            ),
            ItemType.ERROR: cast(
                Callable[[ItemEvent], Awaitable[None]], handle_error_item
            ),
        }
        return EventDispatcher(handlers=handlers, item_handlers=item_handlers)
