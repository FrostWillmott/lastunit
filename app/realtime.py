from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol

Event = tuple[str, dict[str, object]]

PING_EVENT = "ping"
PING_INTERVAL_SECONDS = 15.0
QUEUE_MAXSIZE = 100


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
            try:
                queue.put_nowait((event, payload))
            except asyncio.QueueFull:
                # A subscriber too far behind (or dead but not yet detected):
                # drop the oldest event rather than grow memory without bound.
                # The client refetches on reconnect, so a dropped event is safe.
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                queue.put_nowait((event, payload))

    def subscribe(self) -> AsyncIterator[Event]:
        # Register eagerly so a publish that happens right after subscribe() is
        # still delivered to this subscriber.
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._subscribers.add(queue)
        return self._iterate(queue)

    async def _iterate(self, queue: asyncio.Queue[Event]) -> AsyncIterator[Event]:
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=PING_INTERVAL_SECONDS
                    )
                except TimeoutError:
                    # Keepalive: an idle stream must still see a write so a
                    # dropped connection is detected and proxies don't time out.
                    yield (PING_EVENT, {})
                    continue
                yield event
        finally:
            self._subscribers.discard(queue)
