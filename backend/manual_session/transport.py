from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Iterable, Optional, Set

from fastapi import WebSocket

from .models import AppState, ChatMessage


class SessionTransport:
    """
    Manage websocket clients and provide broadcast utilities for session events.
    """

    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()
        self._broadcast_lock = asyncio.Lock()

    @property
    def clients(self) -> Set[WebSocket]:
        return self._clients

    async def register(self, websocket: WebSocket) -> None:
        self._clients.add(websocket)

    def unregister(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        async with self._broadcast_lock:
            dead_clients: Set[WebSocket] = set()
            message = json.dumps(payload, ensure_ascii=False)
            for client in list(self._clients):
                try:
                    await client.send_text(message)
                except Exception:
                    dead_clients.add(client)
            for client in dead_clients:
                self._clients.discard(client)

    async def broadcast_messages(
        self,
        session_id: str,
        messages: Iterable[ChatMessage],
    ) -> None:
        await self.broadcast(
            {
                "type": "message",
                "session_id": session_id,
                "messages": [message.model_dump() for message in messages],
            }
        )

    async def broadcast_token_usage(
        self,
        session_id: str,
        usage: Dict[str, Any],
    ) -> None:
        await self.broadcast(
            {"type": "token_update", "session_id": session_id, "usage": usage}
        )

    async def broadcast_state(self, state: AppState) -> None:
        await self.broadcast({"type": "state", "data": state.model_dump()})

    async def send_initial_state(self, websocket: WebSocket, state: AppState) -> None:
        await websocket.send_text(
            json.dumps(
                {"type": "state", "data": state.model_dump()},
                ensure_ascii=False,
            )
        )
