from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.deps import get_broadcaster
from app.realtime import PING_EVENT, Broadcaster

router = APIRouter(tags=["events"])


@router.get("/events")
async def events(
    broadcaster: Broadcaster = Depends(get_broadcaster),
) -> StreamingResponse:
    async def generate() -> AsyncIterator[str]:
        async for event, payload in broadcaster.subscribe():
            if event == PING_EVENT:
                yield ": ping\n\n"
            else:
                yield f"event: {event}\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
