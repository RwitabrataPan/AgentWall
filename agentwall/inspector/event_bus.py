from __future__ import annotations

import asyncio
from typing import Set


class EventBus:
    """In-process pub/sub for Inspector WebSocket push notifications.

    Thread-safe publish from sync interceptor thread via call_soon_threadsafe.
    No external infrastructure required.
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: Set[asyncio.Queue] = set()

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self) -> None:
        """Notify all WS subscribers. Safe to call from any thread."""
        if self._loop is None or not self._subscribers:
            return
        msg = {"type": "refresh"}
        for q in list(self._subscribers):
            try:
                self._loop.call_soon_threadsafe(q.put_nowait, msg)
            except RuntimeError:
                pass  # loop closed

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)


_bus = EventBus()


def get_bus() -> EventBus:
    return _bus
