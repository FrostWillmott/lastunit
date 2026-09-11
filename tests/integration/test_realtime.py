from __future__ import annotations

import asyncio
import socket
from datetime import UTC, datetime, timedelta

import httpx
import uvicorn
from sqlalchemy import select

from app.clock import FrozenClock
from app.db import SessionFactory
from app.main import create_app
from app.models.enums import UserRole
from app.models.user import User
from app.realtime import InProcessBroadcaster
from app.scheduler import run_once
from app.services.auth import ensure_user
from app.services.cart import reserve
from app.services.sales import create_sale

_SHOP = ("shop@example.com", "shop-password")
_BUYER = ("buyer@example.com", "buyer-password")


async def _ensure_user(email: str, password: str, role: str) -> None:
    async with SessionFactory() as session:
        await ensure_user(session, email, password, role)


async def _login(client: httpx.AsyncClient, email: str, password: str) -> None:
    response = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text


def _client(
    broadcaster: InProcessBroadcaster,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=create_app(
                clock=FrozenClock(datetime(2026, 6, 1, 12, tzinfo=UTC)),
                broadcaster=broadcaster,
            )
        ),
        base_url="http://test",
    )


async def test_stock_event_reaches_second_client() -> None:
    broadcaster = InProcessBroadcaster()
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    await _ensure_user(*_BUYER, UserRole.BUYER.value)

    async with _client(broadcaster) as client:
        sub1 = broadcaster.subscribe()
        sub2 = broadcaster.subscribe()

        await _login(client, *_SHOP)
        sale = await client.post(
            "/api/sales",
            json={
                "title": "Flash sale",
                "price_minor": 1000,
                "quantity": 5,
                "timezone": "UTC",
                "starts_at": "2026-06-01T11:00:00",
                "ends_at": "2026-06-01T13:00:00",
            },
        )
        sale_id = int(sale.json()["id"])

        await _login(client, *_BUYER)
        reserved = await client.post(f"/api/sales/{sale_id}/reserve")
        assert reserved.status_code == 201

        event1, payload1 = await anext(sub1)
        event2, payload2 = await anext(sub2)
        assert event1 == "stock_changed"
        assert event2 == "stock_changed"
        assert payload1["sale_id"] == sale_id
        assert payload2["sale_id"] == sale_id


async def test_hold_expiry_broadcasts() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    broadcaster = InProcessBroadcaster()

    async with SessionFactory() as session:
        await ensure_user(session, "buyer@example.com", "pw", UserRole.BUYER.value)
        sale = await create_sale(
            session,
            title="Last one",
            price_minor=1000,
            quantity=1,
            tz_name="UTC",
            starts_at_local=datetime(2026, 6, 1, 11, 0),
            ends_at_local=datetime(2026, 6, 1, 13, 0),
        )
        buyer = (
            await session.execute(select(User).where(User.email == "buyer@example.com"))
        ).scalar_one()
        await reserve(session, sale.id, buyer.id, now, broadcaster)
        sale_id = sale.id

    sub = broadcaster.subscribe()
    async with SessionFactory() as session:
        expired = await run_once(session, now + timedelta(minutes=11), broadcaster)
        assert expired == 1

    event, payload = await anext(sub)
    assert event == "stock_changed"
    assert payload["sale_id"] == sale_id


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def test_sse_smoke_real_server() -> None:
    broadcaster = InProcessBroadcaster()
    port = _free_port()
    config = uvicorn.Config(
        create_app(broadcaster=broadcaster),
        host="127.0.0.1",
        port=port,
        log_level="error",
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:  # noqa: ASYNC110  (poll for uvicorn readiness; no public event)
        await asyncio.sleep(0.01)

    try:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "GET", f"http://127.0.0.1:{port}/api/events"
            ) as response:
                await broadcaster.publish("stock_changed", {"sale_id": 1})
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        assert line == "event: stock_changed"
                        break
    finally:
        server.should_exit = True
        await task
