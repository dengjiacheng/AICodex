"""
Manual session package exposing the service façade and supporting primitives.
"""

from .errors import (
    CommandUnavailableError,
    InvalidSessionInputError,
    ManualSessionError,
    SessionConflictError,
    SessionNotFoundError,
    WorkspaceNotFoundError,
)
from .manager import ManualSessionManager
from .models import (
    AppState,
    ChatMessage,
    ConfigState,
    ConfigPayload,
    MessagePart,
    MessagePayload,
    RoleTemplate,
    SessionCreate,
    SessionRecord,
    SessionUpdate,
    WorkspacePayload,
)
from .service import ManualSessionService
from .transport import SessionTransport

__all__ = [
    "ManualSessionService",
    "ManualSessionManager",
    "SessionTransport",
    "AppState",
    "ChatMessage",
    "ConfigState",
    "ConfigPayload",
    "MessagePart",
    "MessagePayload",
    "RoleTemplate",
    "SessionCreate",
    "SessionRecord",
    "SessionUpdate",
    "WorkspacePayload",
    "ManualSessionError",
    "SessionNotFoundError",
    "SessionConflictError",
    "CommandUnavailableError",
    "InvalidSessionInputError",
    "WorkspaceNotFoundError",
]
