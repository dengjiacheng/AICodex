from __future__ import annotations

import logging
import asyncio
from typing import Awaitable, Callable, Dict, Optional, List, TypeVar

from backend.codex_client.events import CodexEvent, EventKind, ItemEvent, ItemType
from backend.codex_client.runner import to_async_generator
from backend.codex_client.config import CodexExecConfig

LOGGER = logging.getLogger(__name__)

EventHandler = Callable[[CodexEvent], Awaitable[None]]
ItemHandler = Callable[[ItemEvent], Awaitable[None]]
EventT = TypeVar("EventT", CodexEvent, ItemEvent)


class EventDispatcher:
    """
    Routes Codex events to registered async handlers.

    - Handlers can be registered per EventKind.
    - Item events support per ItemType handlers as a refinement.
    - A default handler is invoked when no specific handler exists.
    - Handler errors are logged but do not halt the stream.
    """

    def __init__(
        self,
        *,
        handlers: Optional[Dict[EventKind, EventHandler]] = None,
        item_handlers: Optional[Dict[ItemType, ItemHandler]] = None,
        default_handler: Optional[EventHandler] = None,
    ) -> None:
        self._handlers: Dict[EventKind, EventHandler] = dict(handlers or {})
        self._item_handlers: Dict[ItemType, ItemHandler] = dict(item_handlers or {})
        self._default = default_handler

    def register(
        self, kind: EventKind, handler: EventHandler, *, replace: bool = True
    ) -> None:
        if not replace and kind in self._handlers:
            raise ValueError(f"Handler for {kind} already registered")
        self._handlers[kind] = handler

    def register_item_handler(
        self, item_type: ItemType, handler: ItemHandler, *, replace: bool = True
    ) -> None:
        if not replace and item_type in self._item_handlers:
            raise ValueError(f"Handler for {item_type} already registered")
        self._item_handlers[item_type] = handler

    async def dispatch(self, event: CodexEvent) -> None:
        handler = None

        if isinstance(event, ItemEvent) and event.item_type:
            handler = self._item_handlers.get(event.item_type)
            if handler:
                await self._safe_call(handler, event)
                return

        handler = self._handlers.get(event.kind, self._default)
        if handler:
            await self._safe_call(handler, event)

    async def _safe_call(
        self, handler: Callable[[EventT], Awaitable[None]], event: EventT
    ) -> None:
        try:
            await handler(event)
        except Exception:  # pragma: no cover - safety net
            LOGGER.exception("Handler %s failed for event %s", handler, event)


async def consume_events(
    config: CodexExecConfig,
    *,
    prompt: str,
    dispatcher: EventDispatcher,
    resume_session: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    process_ref: Optional[List[asyncio.subprocess.Process]] = None,
) -> None:
    """Iterate through Codex events and forward them to the dispatcher."""

    async for event in to_async_generator(
        config,
        prompt,
        resume_session=resume_session,
        env=env,
        process_ref=process_ref,
    ):
        await dispatcher.dispatch(event)
