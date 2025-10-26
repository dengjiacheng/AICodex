from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, List, Optional

from backend.codex_client.command_builder import build_exec_command
from backend.codex_client.config import CodexExecConfig
from backend.codex_client.events import (
    CodexEvent,
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
    TurnUsage,
)

LOGGER = logging.getLogger(__name__)


async def to_async_generator(
    config: CodexExecConfig,
    prompt: str,
    *,
    resume_session: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    process_ref: Optional[List[asyncio.subprocess.Process]] = None,
) -> AsyncGenerator[CodexEvent, None]:
    command = build_exec_command(config, resume_session=resume_session)

    yield RunnerCommandEvent(kind=EventKind.RUNNER_COMMAND, command=command)

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
        env=env,
    )

    if process_ref is not None:
        process_ref.append(process)

    yield ProcessStartedEvent(kind=EventKind.PROCESS_STARTED, pid=process.pid)

    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None

    # Feed prompt via stdin then close the pipe.
    process.stdin.write(prompt.encode("utf-8"))
    process.stdin.write(b"\n")
    await process.stdin.drain()
    process.stdin.close()

    queue: asyncio.Queue[CodexEvent] = asyncio.Queue()

    async def read_stdout() -> None:
        stream = process.stdout
        while True:
            try:
                line = await stream.readline()
            except asyncio.LimitOverrunError as exc:
                chunk = await stream.read(exc.consumed)
                if chunk:
                    await queue.put(
                        TextStreamEvent(
                            kind=EventKind.STDOUT_NON_JSON, text=chunk.decode()
                        )
                    )
                continue
            if not line:
                break
            text = line.decode(errors="replace").strip()
            if not text:
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                await queue.put(
                    TextStreamEvent(kind=EventKind.STDOUT_NON_JSON, text=text)
                )
                continue
            await queue.put(_map_json_event(data))

    async def read_stderr() -> None:
        stream = process.stderr
        while True:
            line = await stream.readline()
            if not line:
                break
            await queue.put(
                TextStreamEvent(
                    kind=EventKind.STDERR_LINE, text=line.decode(errors="replace")
                )
            )

    tasks = [
        asyncio.create_task(read_stdout()),
        asyncio.create_task(read_stderr()),
    ]

    try:
        while True:
            if process.stdout.at_eof() and process.stderr.at_eof() and queue.empty():
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                if all(t.done() for t in tasks) and queue.empty():
                    break
                continue
            if event:
                yield event
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    returncode = await process.wait()
    yield ProcessFinishedEvent(
        kind=EventKind.PROCESS_FINISHED, returncode=returncode
    )

    if returncode:
        yield TurnFailedEvent(
            kind=EventKind.TURN_FAILED,
            message=f"Codex exited with return code {returncode}",
        )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _map_json_event(payload: Dict) -> CodexEvent:
    event_type = payload.get("type")

    if event_type == "thread.started":
        return ThreadStartedEvent(
            kind=EventKind.THREAD_STARTED,
            thread_id=str(payload.get("thread_id")) if payload.get("thread_id") else None,
            raw=payload,
        )

    if event_type == "turn.started":
        return CodexEvent(kind=EventKind.TURN_STARTED, raw=payload)

    if event_type == "turn.completed":
        usage_payload = payload.get("usage") or {}
        usage = TurnUsage(
            input_tokens=int(usage_payload.get("input_tokens") or 0),
            cached_input_tokens=int(usage_payload.get("cached_input_tokens") or 0),
            output_tokens=int(usage_payload.get("output_tokens") or 0),
            reasoning_output_tokens=int(
                usage_payload.get("reasoning_output_tokens") or 0
            ),
            total_tokens=int(usage_payload.get("total_tokens") or 0),
        )
        return TurnCompletedEvent(
            kind=EventKind.TURN_COMPLETED, usage=usage, raw=payload
        )

    if event_type == "turn.failed":
        error = payload.get("error") or {}
        message = error.get("message") or error or "Codex turn failed"
        return TurnFailedEvent(kind=EventKind.TURN_FAILED, message=str(message), raw=payload)

    if event_type in {"item.started", "item.updated", "item.completed"}:
        item = payload.get("item") or {}
        item_id = item.get("id")
        item_type = _resolve_item_type(item.get("type"))
        return ItemEvent(
            kind=EventKind(event_type),
            item_id=item_id,
            item_type=item_type,
            payload=item,
            raw=payload,
        )

    if event_type == "error":
        message = payload.get("message") or payload
        return TurnFailedEvent(
            kind=EventKind.STREAM_ERROR,
            message=str(message),
            raw=payload,
        )

    return CodexEvent(kind=EventKind.STDOUT_NON_JSON, raw=payload)


def _resolve_item_type(value: Optional[str]) -> Optional[ItemType]:
    if not value:
        return None
    try:
        return ItemType(value)
    except ValueError:
        LOGGER.debug("Unknown item type: %s", value)
        return None
