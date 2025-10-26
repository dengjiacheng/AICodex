from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Sequence


# --------------------------------------------------------------------------- #
# Event categorisation
# --------------------------------------------------------------------------- #


class EventKind(enum.Enum):
    RUNNER_COMMAND = "runner.command"
    PROCESS_STARTED = "process.started"
    PROCESS_FINISHED = "process.finished"
    STDOUT_NON_JSON = "stdout.non_json"
    STDERR_LINE = "stderr.line"
    THREAD_STARTED = "thread.started"
    TURN_STARTED = "turn.started"
    TURN_COMPLETED = "turn.completed"
    TURN_FAILED = "turn.failed"
    ITEM_STARTED = "item.started"
    ITEM_UPDATED = "item.updated"
    ITEM_COMPLETED = "item.completed"
    STREAM_ERROR = "error"


class ItemType(enum.Enum):
    AGENT_MESSAGE = "agent_message"
    REASONING = "reasoning"
    COMMAND_EXECUTION = "command_execution"
    FILE_CHANGE = "file_change"
    MCP_TOOL_CALL = "mcp_tool_call"
    WEB_SEARCH = "web_search"
    TODO_LIST = "todo_list"
    ERROR = "error"


# --------------------------------------------------------------------------- #
# Event payloads
# --------------------------------------------------------------------------- #


@dataclass
class CodexEvent:
    kind: EventKind
    timestamp: datetime = field(default_factory=datetime.utcnow)
    raw: Optional[Dict] = None


@dataclass
class RunnerCommandEvent(CodexEvent):
    command: Sequence[str] = field(default_factory=list)


@dataclass
class ProcessStartedEvent(CodexEvent):
    pid: int = 0


@dataclass
class ProcessFinishedEvent(CodexEvent):
    returncode: Optional[int] = None


@dataclass
class TextStreamEvent(CodexEvent):
    text: str = ""


@dataclass
class ThreadStartedEvent(CodexEvent):
    thread_id: Optional[str] = None


@dataclass
class TurnUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class TurnCompletedEvent(CodexEvent):
    usage: TurnUsage = field(default_factory=TurnUsage)


@dataclass
class TurnFailedEvent(CodexEvent):
    message: str = ""


@dataclass
class ItemEvent(CodexEvent):
    item_id: Optional[str] = None
    item_type: Optional[ItemType] = None
    payload: Dict = field(default_factory=dict)

