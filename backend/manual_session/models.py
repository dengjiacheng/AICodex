from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from asyncio.subprocess import Process

from pydantic import BaseModel


def utc_now_iso() -> str:
    """
    Return a UTC ISO8601 timestamp with Z suffix.
    """
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


class MessagePart(BaseModel):
    text: str
    is_error: bool = False


class ChatMessage(BaseModel):
    id: str
    role: str
    timestamp: str
    parts: List[MessagePart]
    forwarded_by: Optional[str] = None
    origin_session: Optional[str] = None
    kind: Optional[str] = None


class ConfigState(BaseModel):
    command: str
    args: str
    workspace: str
    model: str
    reasoning: str
    summary: str
    approval: str
    sandbox: str



class AppState(BaseModel):
    workspace: str
    config: ConfigState
    sessions: List[Dict[str, object]]


@dataclass
class SessionRecord:
    """
    In-memory context for a manual Codex session.

    Holds configuration, accumulated messages, active process tracking,
    and token usage statistics.
    """

    id: str
    role: Dict[str, str]
    command: str
    workspace: str
    args: str = ""
    model: str = "gpt-5-codex"
    reasoning: str = "high"
    summary: str = "auto"
    approval: str = "never"
    sandbox: str = "danger-full-access"
    status: str = "stopped"
    status_detail: Optional[str] = None
    messages: List[ChatMessage] = field(default_factory=list)
    thread_id: Optional[str] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    active_process: Optional[Process] = None
    token_usage: Optional[Dict[str, object]] = None

    def serialize(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "role": self.role,
            "command": self.command,
            "args": self.args,
            "workspace": self.workspace,
            "model": self.model,
            "reasoning": self.reasoning,
            "summary": self.summary,
            "approval": self.approval,
            "sandbox": self.sandbox,
            "status": self.status,
            "status_detail": self.status_detail,
            "messages": [message.model_dump() for message in self.messages],
            "token_usage": self.token_usage,
            "thread_id": self.thread_id,
        }

    def append_message(self, message: ChatMessage) -> None:
        self.messages.append(message)

    def append_system(
        self,
        text: str,
        *,
        kind: Optional[str] = None,
    ) -> ChatMessage:
        message = ChatMessage(
            id=str(uuid.uuid4()),
            role="system",
            timestamp=utc_now_iso(),
            parts=[MessagePart(text=f"{text}\n")],
            kind=kind,
        )
        self.messages.append(message)
        return message

    def append_codex_output(
        self,
        chunk: str,
        *,
        is_error: bool,
        kind: Optional[str] = None,
    ) -> ChatMessage:
        chunk = chunk.replace("\r\n", "\n").replace("\r", "\n")
        message = ChatMessage(
            id=str(uuid.uuid4()),
            role="codex",
            timestamp=utc_now_iso(),
            parts=[MessagePart(text=chunk, is_error=is_error)],
            kind=kind,
        )
        self.messages.append(message)
        return message

    def ensure_workspace(self, fallback: str) -> Path:
        workspace = Path(self.workspace or fallback)
        return workspace


class SessionCreate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None


class SessionUpdate(BaseModel):
    command: Optional[str] = None
    args: Optional[str] = None
    workspace: Optional[str] = None
    model: Optional[str] = None
    reasoning: Optional[str] = None
    summary: Optional[str] = None
    approval: Optional[str] = None
    sandbox: Optional[str] = None


class WorkspacePayload(BaseModel):
    path: str


class MessagePayload(BaseModel):
    text: str
    forwarded_by: Optional[str] = None


class ConfigPayload(BaseModel):
    command: Optional[str] = None
    args: Optional[str] = None
    workspace: Optional[str] = None
    model: Optional[str] = None
    reasoning: Optional[str] = None
    summary: Optional[str] = None
    approval: Optional[str] = None
    sandbox: Optional[str] = None
