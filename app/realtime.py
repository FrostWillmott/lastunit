from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol

Event = tuple[str, dict[str, object]]


class Broadcaster(Protocol):
    async def publish(self, event: str, payload: dict[str, object]) -> None:
        """Publish an event to every connected client."""

    def subscribe(self) -> AsyncIterator[Event]:
        """Yield events as they are published (used by the SSE endpoint)."""


class NoopBroadcaster:
    """Used in tests that only exercise the publish call site."""

    async def publish(self, event: str, payload: dict[str, object]) -> None:
        return None

    async def subscribe(self) -> AsyncIterator[Event]:
        if False:  # a no-op broadcaster never emits
            yield ("", {})
        return


class InProcessBroadcaster:
    """Fan events out to every subscriber in this process (single-worker demo)."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()

    async def publish(self, event: str, payload: dict[str, object]) -> None:
        for queue in list(self._subscribers):
            queue.put_nowait((event, payload))

    def subscribe(self) -> AsyncIterator[Event]:
        # Register eagerly so a publish that happens right after subscribe() is
        # still delivered to this subscriber.
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._subscribers.add(queue)
        return self._iterate(queue)

    async def _iterate(self, queue: asyncio.Queue[Event]) -> AsyncIterator[Event]:
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)
