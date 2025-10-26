import asyncio
import sys
from pathlib import Path

import pytest

from backend.codex_client import (
    CodexExecConfig,
    EventDispatcher,
    EventKind,
    ItemEvent,
    ItemType,
    consume_events,
    to_async_generator,
)
from backend.codex_client.events import TextStreamEvent

FAKE_CLI = Path(__file__).with_name("fake_codex_cli.py")


@pytest.mark.asyncio
async def test_dispatcher_routes_events_by_kind():
    config = CodexExecConfig(command=sys.executable, args=(str(FAKE_CLI),))

    seen_kinds = []

    async def on_any(event):
        seen_kinds.append(event.kind)

    dispatcher = EventDispatcher(default_handler=on_any)

    await consume_events(config, prompt="hello dispatcher", dispatcher=dispatcher)

    assert EventKind.THREAD_STARTED in seen_kinds
    assert EventKind.TURN_COMPLETED in seen_kinds
    assert EventKind.ITEM_COMPLETED in seen_kinds


@pytest.mark.asyncio
async def test_dispatcher_item_specific_handler():
    config = CodexExecConfig(command=sys.executable, args=(str(FAKE_CLI),))

    item_payloads = []

    async def on_command(event: ItemEvent):
        item_payloads.append(event.payload.get("command"))

    async def on_default(event):
        pass  # pragma: no cover

    dispatcher = EventDispatcher(
        default_handler=on_default,
        item_handlers={ItemType.COMMAND_EXECUTION: on_command},
    )

    async for event in to_async_generator(config, prompt="with item handler"):
        await dispatcher.dispatch(event)

    assert "echo hello" in item_payloads


@pytest.mark.asyncio
async def test_dispatcher_logs_and_continues(caplog):
    config = CodexExecConfig(command=sys.executable, args=(str(FAKE_CLI),))

    caplog.set_level("ERROR")

    async def faulty_handler(event):
        raise RuntimeError("boom")

    dispatcher = EventDispatcher(
        handlers={EventKind.THREAD_STARTED: faulty_handler},
        default_handler=lambda _: asyncio.sleep(0),
    )

    await consume_events(config, prompt="trigger error", dispatcher=dispatcher)

    assert any(
        record.exc_info and isinstance(record.exc_info[1], RuntimeError)
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_dispatcher_handles_non_json_stdout():
    config = CodexExecConfig(command=sys.executable, args=(str(FAKE_CLI),))

    banner_lines = []

    async def on_text(event: TextStreamEvent):
        banner_lines.append(event.text)

    dispatcher = EventDispatcher(
        handlers={EventKind.STDOUT_NON_JSON: on_text},
    )

    await consume_events(config, prompt="banner check", dispatcher=dispatcher)

    assert any("banner check" in line for line in banner_lines)
