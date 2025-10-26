from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional

from backend.codex_client import (
    CodexExecConfig,
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
    to_async_generator,
)

logger = logging.getLogger(__name__)


@dataclass
class RunOptions:
    workspace: Path
    command: str
    args: List[str] = field(default_factory=list)
    thread_id: Optional[str] = None
    model: Optional[str] = None
    sandbox: Optional[str] = None
    reasoning: Optional[str] = None
    summary_style: Optional[str] = None
    approval: Optional[str] = None
    extra_args: List[str] = field(default_factory=list)
    extra_configs: Dict[str, str] = field(default_factory=dict)
    env_overrides: Dict[str, str] = field(default_factory=dict)
    prompt_argument: Optional[str] = None


class CodexCliRunner:
    """
    Thin wrapper around `codex exec --json`, backed by the shared Codex client.

    Compatibility: yields legacy dictionary events so that existing orchestrator
    logic continues to function without major changes.
    """

    def __init__(self) -> None:
        pass

    async def run(
        self,
        options: RunOptions,
        process_ref: Optional[List[asyncio.subprocess.Process]] = None,
    ) -> AsyncGenerator[Dict[str, object], None]:
        config = CodexExecConfig(
            command=options.command,
            args=tuple(options.args),
            workspace=str(options.workspace),
            model=options.model,
            reasoning_effort=options.reasoning,
            summary_style=options.summary_style,
            approval_policy=options.approval,
            sandbox=options.sandbox,
            extra_args=tuple(options.extra_args),
            extra_configs=options.extra_configs,
        )

        prompt = options.prompt_argument or ""
        env = options.env_overrides or None

        async for event in to_async_generator(
            config,
            prompt=prompt,
            resume_session=options.thread_id,
            env=env,
            process_ref=process_ref,
        ):
            yield _event_to_dict(event, workspace=str(options.workspace))


def _event_to_dict(event: CodexEvent, workspace: str) -> Dict[str, object]:
    if isinstance(event, RunnerCommandEvent):
        return {
            "type": "runner.command",
            "command": list(event.command),
            "workspace": workspace,
        }
    if isinstance(event, ProcessStartedEvent):
        return {
            "type": "process.started",
            "pid": event.pid,
        }
    if isinstance(event, ProcessFinishedEvent):
        return {
            "type": "process.finished",
            "returncode": event.returncode,
        }
    if isinstance(event, TextStreamEvent):
        stream = "stdout" if event.kind == EventKind.STDOUT_NON_JSON else "stderr"
        return {
            "type": "runner.raw_output",
            "stream": stream,
            "text": event.text,
        }
    if isinstance(event, ThreadStartedEvent):
        payload = {
            "type": "thread.started",
        }
        if event.thread_id:
            payload["thread_id"] = event.thread_id
        return payload
    if isinstance(event, TurnCompletedEvent):
        usage = event.usage
        return {
            "type": "turn.completed",
            "usage": {
                "input_tokens": usage.input_tokens,
                "cached_input_tokens": usage.cached_input_tokens,
                "output_tokens": usage.output_tokens,
                "reasoning_output_tokens": usage.reasoning_output_tokens,
                "total_tokens": usage.total_tokens,
            },
        }
    if isinstance(event, TurnFailedEvent):
        if event.kind == EventKind.STREAM_ERROR:
            return {
                "type": "error",
                "message": event.message,
            }
        return {
            "type": "turn.failed",
            "error": {"message": event.message},
        }
    if isinstance(event, ItemEvent):
        return {
            "type": event.kind.value,
            "item": event.payload or {},
        }
    if event.kind == EventKind.TURN_STARTED:
        return {"type": "turn.started"}

    # Fallback for any unrecognised event.
    return {
        "type": event.kind.value,
        "raw": event.raw,
    }
