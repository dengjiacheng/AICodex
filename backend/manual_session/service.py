from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException

from .errors import ManualSessionError
from .manager import ManualSessionManager
from .models import AppState, SessionRecord
from .transport import SessionTransport


class ManualSessionService:
    """
    High-level façade exposed to FastAPI routes.
    """

    def __init__(self, manager: Optional[ManualSessionManager] = None) -> None:
        self.manager = manager or ManualSessionManager()

    # ------------------------------------------------------------------ #
    # Convenience accessors
    # ------------------------------------------------------------------ #
    @property
    def transport(self) -> SessionTransport:
        return self.manager.transport

    def serialize(self) -> AppState:
        return self.manager.serialize()

    def get_auto_task_config(self) -> Dict[str, str]:
        return self.manager.get_auto_task_config()

    # ------------------------------------------------------------------ #
    # Wrapped operations with unified error handling
    # ------------------------------------------------------------------ #
    async def create_session(self, payload: Dict[str, Any]) -> SessionRecord:
        return await self._wrap(self.manager.create_session(payload))

    async def update_session(
        self, session_id: str, payload: Dict[str, Any]
    ) -> SessionRecord:
        return await self._wrap(self.manager.update_session(session_id, payload))

    async def start_session(self, session_id: str) -> SessionRecord:
        return await self._wrap(self.manager.start_session(session_id))

    async def stop_session(self, session_id: str) -> SessionRecord:
        return await self._wrap(self.manager.stop_session(session_id))

    async def delete_session(self, session_id: str) -> None:
        await self._wrap(self.manager.delete_session(session_id))

    async def send_input(
        self, session_id: str, text: str, forwarded_by: Optional[str]
    ) -> SessionRecord:
        return await self._wrap(self.manager.send_input(session_id, text, forwarded_by))

    async def clear_session(self, session_id: str) -> SessionRecord:
        return await self._wrap(self.manager.clear_session(session_id))

    async def save_session(self, session_id: str) -> str:
        path = await self._wrap(self.manager.save_session(session_id))
        return str(path)

    async def update_workspace(self, path: str) -> None:
        await self._wrap(self.manager.update_workspace(path))

    async def apply_config(self, payload: Dict[str, Any]) -> None:
        await self._wrap(self.manager.apply_config(payload))

    async def select_directory(self) -> str:
        return await self._wrap(self.manager.select_directory())

    async def _wrap(self, coro):
        try:
            return await coro
        except ManualSessionError as exc:
            raise exc.to_http_exception() from exc
        except HTTPException:
            raise
