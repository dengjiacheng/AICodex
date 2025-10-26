"""
Shared Codex CLI client utilities.

This package currently exposes the configuration data model and command
assembly helpers used by both the manual session flow and the auto-task
orchestrator.
"""

from backend.codex_client.command_builder import build_exec_command
from backend.codex_client.config import CodexExecConfig, PromptSource
from backend.codex_client.dispatcher import (
    EventDispatcher,
    EventHandler,
    ItemHandler,
    consume_events,
)
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
)
from backend.codex_client.runner import to_async_generator

__all__ = [
    "CodexExecConfig",
    "PromptSource",
    "build_exec_command",
    "to_async_generator",
    "EventDispatcher",
    "consume_events",
    "EventKind",
    "ItemType",
    "CodexEvent",
    "RunnerCommandEvent",
    "ProcessStartedEvent",
    "ProcessFinishedEvent",
    "TextStreamEvent",
    "ThreadStartedEvent",
    "TurnCompletedEvent",
    "TurnFailedEvent",
    "ItemEvent",
]
