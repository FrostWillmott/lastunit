from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol

Event = tuple[str, dict[str, object]]

PING_EVENT = "ping"
PING_INTERVAL_SECONDS = 15.0
QUEUE_MAXSIZE = 100


class Broadcaster(Protocol):
    async def publish(
        self, event: str, payload: dict[str, object], user_id: int | None = None
    ) -> None:
        """Publish an event. ``user_id=None`` fans out to every subscriber;
        otherwise only that user's connections receive it."""

    def subscribe(self, user_id: int | None = None) -> AsyncIterator[Event]:
        """Yield events as they are published. ``user_id=None`` subscribes to
        public events only; otherwise also to that user's scoped events."""


class NoopBroadcaster:
    """Used in tests that only exercise the publish call site."""

    async def publish(
        self, event: str, payload: dict[str, object], user_id: int | None = None
    ) -> None:
        return None

    async def subscribe(self, user_id: int | None = None) -> AsyncIterator[Event]:
        if False:  # a no-op broadcaster never emits
            yield ("", {})
        return


class InProcessBroadcaster:
    """Fan events out to subscribers in this process (single-worker demo).

    A subscriber is tagged with a user id: it receives every public event plus
    the ``order_status`` events addressed to that user, never another user's.
    """

    def __init__(self) -> None:
        self._subscribers: dict[asyncio.Queue[Event], int | None] = {}

    async def publish(
        self, event: str, payload: dict[str, object], user_id: int | None = None
    ) -> None:
        for queue, sub_user in list(self._subscribers.items()):
            if user_id is not None and sub_user != user_id:
                continue
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

    def subscribe(self, user_id: int | None = None) -> AsyncIterator[Event]:
        # Register eagerly so a publish that happens right after subscribe() is
        # still delivered to this subscriber.
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._subscribers[queue] = user_id
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
            self._subscribers.pop(queue, None)
