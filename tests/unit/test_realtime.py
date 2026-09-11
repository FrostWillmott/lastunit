from __future__ import annotations

from pytest import MonkeyPatch

import app.realtime as realtime
from app.realtime import PING_EVENT, InProcessBroadcaster


async def test_broadcaster_emits_ping_when_idle(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(realtime, "PING_INTERVAL_SECONDS", 0.01)
    broadcaster = InProcessBroadcaster()
    sub = broadcaster.subscribe()

    event, payload = await anext(sub)
    assert event == PING_EVENT
    assert payload == {}


async def test_broadcaster_drops_oldest_when_queue_full(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(realtime, "QUEUE_MAXSIZE", 2)
    broadcaster = InProcessBroadcaster()
    sub = broadcaster.subscribe()

    await broadcaster.publish("e", {"n": 1})
    await broadcaster.publish("e", {"n": 2})
    await broadcaster.publish("e", {"n": 3})  # overflows: drops the first event

    received: list[object] = []
    async for _event, payload in sub:
        received.append(payload["n"])
        if len(received) == 2:
            break
    assert received == [2, 3]
