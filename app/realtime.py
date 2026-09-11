from __future__ import annotations

from typing import Protocol


class Broadcaster(Protocol):
    async def publish(self, event: str, payload: dict[str, object]) -> None:
        """Publish an event to connected clients."""


class NoopBroadcaster:
    """No-op broadcaster until the real SSE broadcaster lands (commit 18)."""

    async def publish(self, event: str, payload: dict[str, object]) -> None:
        return None
