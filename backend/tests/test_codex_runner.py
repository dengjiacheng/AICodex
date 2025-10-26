import asyncio
import sys
from pathlib import Path

import pytest

from backend.codex_client import CodexExecConfig
from backend.codex_client.events import (
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
)
from backend.codex_client.runner import to_async_generator


FAKE_CLI = Path(__file__).with_name("fake_codex_cli.py")


@pytest.mark.asyncio
async def test_runner_success_sequence():
    config = CodexExecConfig(
        command=sys.executable,
        args=(str(FAKE_CLI),),
    )

    events = []
    async for event in to_async_generator(config, prompt="deploy plan?"):
        events.append(event)

    kinds = [event.kind for event in events]

    assert kinds[0] == EventKind.RUNNER_COMMAND
    assert isinstance(events[0], RunnerCommandEvent)
    assert events[0].command[0] == sys.executable
    assert "exec" in events[0].command

    assert kinds[1] == EventKind.PROCESS_STARTED
    assert isinstance(events[1], ProcessStartedEvent)

    # Expect banner text, thread, turn, item, usage, finish.
    assert EventKind.STDOUT_NON_JSON in kinds
    assert EventKind.THREAD_STARTED in kinds
    assert EventKind.TURN_STARTED in kinds
    assert EventKind.ITEM_STARTED in kinds
    assert EventKind.ITEM_COMPLETED in kinds
    assert EventKind.TURN_COMPLETED in kinds
    assert kinds[-1] == EventKind.PROCESS_FINISHED

    text_events = [event for event in events if isinstance(event, TextStreamEvent)]
    assert text_events and "deploy plan?" in text_events[0].text

    thread_event = next(event for event in events if isinstance(event, ThreadStartedEvent))
    assert thread_event.thread_id == "fake-thread-1"

    item_event = next(
        event for event in events if isinstance(event, ItemEvent) and event.kind == EventKind.ITEM_COMPLETED
    )
    assert item_event.item_type == ItemType.COMMAND_EXECUTION
    assert item_event.payload.get("aggregated_output").strip() == "hello"

    usage_event = next(event for event in events if isinstance(event, TurnCompletedEvent))
    assert usage_event.usage.total_tokens == 15

    assert not any(isinstance(event, TurnFailedEvent) for event in events)


@pytest.mark.asyncio
async def test_runner_failure_emits_turn_failed():
    config = CodexExecConfig(
        command=sys.executable,
        args=(str(FAKE_CLI),),
        extra_args=("--fail",),
    )

    events = []
    async for event in to_async_generator(config, prompt="dry run"):
        events.append(event)

    failure_msgs = [
        event.message for event in events if isinstance(event, TurnFailedEvent)
    ]
    assert any("forced failure" in msg for msg in failure_msgs)
    assert any("return code" in msg for msg in failure_msgs)

    finish_event = next(
        event for event in events if isinstance(event, ProcessFinishedEvent)
    )
    assert finish_event.returncode == 1
