from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

class AutoSessionEventHandler:
    def __init__(
        self,
        orchestrator: "AutoTaskOrchestrator",
        task: "CurrentTask",
        process_holder: List["asyncio.subprocess.Process"],
    ) -> None:
        self.orchestrator = orchestrator
        self.task = task
        self.process_holder = process_holder
        self.events: List[Dict[str, Any]] = []
        self.logger = logging.getLogger(__name__)

    async def handle(self, event: Dict[str, Any]) -> None:
        if self.process_holder and self.orchestrator._current_process is None:
            self.orchestrator._current_process = self.process_holder[0]
        self.events.append(event)
        event_type = event.get("type")
        if event_type == "runner.raw_output":
            self.logger.info("cli stdout/stderr: %s", event.get("text"))
        else:
            self.logger.info(
                "cli.event: task=%s type=%s", self.task.id, event_type
            )
        await self.orchestrator._broadcast(
            {"type": "cli.event", "task_id": self.task.id, "event": event}
        )
        formatted = self._format_cli_event(event)
        if formatted:
            await self.orchestrator._broadcast(
                {
                    "type": "auto_task.message",
                    "task_id": self.task.id,
                    "message": formatted,
                }
            )
        if event_type == "thread.started" and event.get("thread_id"):
            self.orchestrator._thread_id = str(event["thread_id"])

    def finalize(self) -> Dict[str, Any]:
        return self._parse_execution_events(self.events)

    def _format_cli_event(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        event_type = event.get("type")
        timestamp = datetime.utcnow().isoformat()

        if event_type == "runner.command":
            command = " ".join(event.get("command") or [])
            text = "$ " + command if command else "Codex CLI 启动"
            return self.orchestrator._build_cli_message(
                "command", "command_start", text, timestamp
            )
        if event_type == "runner.raw_output":
            text = event.get("text") or ""
            stream = event.get("stream") or "stdout"
            kind = "command_output" if stream == "stdout" else "command_error"
            return self.orchestrator._build_cli_message(
                "command", kind, text, timestamp
            )
        if event_type == "runner.error":
            detail = event.get("details") or event.get("error") or "未知错误"
            return self.orchestrator._build_cli_message(
                "system", "error", detail, timestamp
            )
        if event_type == "process.finished":
            code = event.get("returncode")
            text = f"Codex 进程结束，退出码 {code}"
            return self.orchestrator._build_cli_message(
                "system", "status", text, timestamp
            )
        if event_type == "thread.started":
            thread_id = event.get("thread_id")
            text = f"新线程启动：{thread_id}" if thread_id else "新线程启动"
            return self.orchestrator._build_cli_message(
                "system", "thread_started", text, timestamp
            )
        if event_type == "turn.started":
            return self.orchestrator._build_cli_message(
                "system", "turn_started", "开始新的对话回合", timestamp
            )
        if event_type == "turn.completed":
            usage = event.get("usage") or {}
            inputs = usage.get("input_tokens")
            outputs = usage.get("output_tokens")
            reasoning = usage.get("reasoning_output_tokens")
            parts = [f"输入 {inputs}", f"输出 {outputs}"]
            if reasoning is not None:
                parts.append(f"推理 {reasoning}")
            text = "Token 使用：" + "，".join(parts)
            return self.orchestrator._build_cli_message(
                "system", "turn_completed", text, timestamp
            )
        if event_type in {"item.started", "item.updated", "item.completed"}:
            item = event.get("item") or {}
            item_type = item.get("type") or "unknown"
            status = item.get("status")
            base_kind = f"item_{item_type}"

            if event_type == "item.started":
                if item_type == "command_execution":
                    command = item.get("command") or ""
                    text = f"开始执行命令：{command}"
                    return self.orchestrator._build_cli_message(
                        "command", f"{base_kind}_started", text, timestamp
                    )
                text = f"开始处理 {item_type}"
                return self.orchestrator._build_cli_message(
                    "system", f"{base_kind}_started", text, timestamp
                )

            if event_type == "item.updated":
                aggregated = item.get("aggregated_output")
                if aggregated:
                    text = aggregated
                else:
                    text = f"{item_type} 状态更新：{status or '进行中'}"
                role = (
                    "command"
                    if item_type == "command_execution"
                    else "system"
                )
                return self.orchestrator._build_cli_message(
                    role, f"{base_kind}_updated", text, timestamp
                )

            text = item.get("text") or ""
            if item_type == "agent_message" and text:
                return self.orchestrator._build_cli_message(
                    "codex", "agent_message", text, timestamp
                )
            if item_type == "reasoning" and text:
                return self.orchestrator._build_cli_message(
                    "system", "reasoning", text, timestamp
                )
            if item_type == "command_execution":
                command = item.get("command") or ""
                output = item.get("aggregated_output") or ""
                exit_code = item.get("exit_code")
                message_text = f"$ {command}\n{output}".rstrip()
                if exit_code is not None:
                    message_text += f"\n[退出码 {exit_code}]"
                return self.orchestrator._build_cli_message(
                    "command", "command_execution", message_text, timestamp
                )
            if item_type == "agent_error" and text:
                return self.orchestrator._build_cli_message(
                    "system", "error", text, timestamp
                )
            if text:
                return self.orchestrator._build_cli_message(
                    "system", f"{base_kind}_completed", text, timestamp
                )

        if event_type == "error":
            msg = event.get("message") or event
            return self.orchestrator._build_cli_message(
                "system", "error", f"Codex 错误事件：{msg}", timestamp
            )
        return None

    def _parse_execution_events(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        summary_parts: List[str] = []
        json_payload: Optional[Dict[str, Any]] = None
        return_code: Optional[int] = None
        for event in events:
            if event.get("type") == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message":
                    text = item.get("text") or ""
                    if text:
                        summary_parts.append(text)
            if event.get("type") == "runner.error":
                error_text = event.get("details") or event.get("error") or "CLI 启动失败"
                json_payload = {
                    "status": "failed",
                    "error": error_text,
                }
            if (
                event.get("type") == "runner.raw_output"
                and event.get("stream") == "stdout"
            ):
                text = event.get("text", "")
                try:
                    json_payload = json.loads(text)
                except json.JSONDecodeError:
                    continue
            if event.get("type") == "process.finished":
                return_code = event.get("returncode")
        payload = json_payload or {}
        status = payload.get("status")
        if not status:
            if return_code == 0:
                status = "success"
            else:
                status = "unknown"
        return {
            "status": status,
            "summary_markdown": "\n".join(summary_parts),
            "payload": payload,
            "returncode": return_code,
        }
if TYPE_CHECKING:
    from backend.auto_task.orchestrator import AutoTaskOrchestrator
    from backend.auto_task.types import CurrentTask
