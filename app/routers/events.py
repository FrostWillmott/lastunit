from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.clock import Clock
from app.db import SessionFactory
from app.deps import SESSION_COOKIE, get_broadcaster, get_clock
from app.realtime import PING_EVENT, Broadcaster
from app.services import auth

router = APIRouter(tags=["events"])


@router.get("/events")
async def events(
    request: Request,
    broadcaster: Broadcaster = Depends(get_broadcaster),
    clock: Clock = Depends(get_clock),
) -> StreamingResponse:
    # The stream is public — anyone can watch stock/sale events — but a session
    # cookie scopes order_status to its owner. Resolve the user once, in a
    # short-lived session, so the stream itself holds no DB connection.
    user_id: int | None = None
    token = request.cookies.get(SESSION_COOKIE)
    if token is not None:
        async with SessionFactory() as session:
            user = await auth.user_for_token(session, token, await clock.now(session))
            user_id = user.id if user is not None else None

    async def generate() -> AsyncIterator[str]:
        async for event, payload in broadcaster.subscribe(user_id):
            if event == PING_EVENT:
                yield ": ping\n\n"
            else:
                yield f"event: {event}\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
