from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import uvicorn
from sqlalchemy import select

from app.clock import FrozenClock
from app.db import SessionFactory
from app.main import create_app
from app.models.enums import UserRole
from app.models.user import User
from app.realtime import Event, InProcessBroadcaster
from app.scheduler import run_once
from app.services.auth import ensure_user
from app.services.cart import reserve
from app.services.orders import create_order
from app.services.payments import apply_payment_result, start_payment
from app.services.sales import create_sale

_SHOP = ("shop@example.com", "shop-password")
_BUYER = ("buyer@example.com", "buyer-password")


# The subscription itself never ends, so a short deadline is the only way to say
# "nothing more is pending". Not a wall-clock dependency: every publish here is
# in-process and already done before the drain starts.
_DRAIN_TIMEOUT_SECONDS = 0.05


async def _drain(subscription: AsyncIterator[Event]) -> AsyncIterator[Event]:
    """Yield the events already queued for a subscriber, then stop."""
    while True:
        try:
            yield await asyncio.wait_for(
                anext(subscription), timeout=_DRAIN_TIMEOUT_SECONDS
            )
        except (TimeoutError, StopAsyncIteration):
            return


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


async def test_order_status_is_scoped_to_its_owner() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    broadcaster = InProcessBroadcaster()

    async with SessionFactory() as session:
        await ensure_user(session, "buyer@example.com", "pw", UserRole.BUYER.value)
        buyer = (
            await session.execute(select(User).where(User.email == "buyer@example.com"))
        ).scalar_one()
        sale = await create_sale(
            session,
            title="X",
            price_minor=1000,
            quantity=1,
            tz_name="UTC",
            starts_at_local=datetime(2026, 6, 1, 11, 0),
            ends_at_local=datetime(2026, 6, 1, 13, 0),
        )
        reservation = await reserve(session, sale.id, buyer.id, now, broadcaster)
        order = await create_order(session, reservation.id, buyer.id, "key", now)
        order_id = order.id
        buyer_id = buyer.id

    async with SessionFactory() as session:
        provider_ref, _ = await start_payment(session, order_id, buyer_id, now)

    owner = broadcaster.subscribe(user_id=buyer_id)
    stranger = broadcaster.subscribe(user_id=buyer_id + 1)

    async with SessionFactory() as session:
        await apply_payment_result(session, provider_ref, "approved", now, broadcaster)

    event, payload = await anext(owner)
    assert event == "order_status"
    assert payload["order_id"] == order_id

    # A connection for a different user hears the sale-level event, never this
    # buyer's order_status.
    stranger_events = [event async for event in _drain(stranger)]
    assert "order_status" not in [name for name, _ in stranger_events]


async def test_payment_result_broadcasts_sale_stats_to_everyone() -> None:
    """The shop dashboard is not the buyer, so it cannot hear ``order_status``.

    A settled payment moves sold/revenue/pending without changing ``available``
    (that was decremented at reserve time), so an unscoped ``sale_stats`` is the
    only thing that tells an open dashboard to refetch.
    """
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    broadcaster = InProcessBroadcaster()

    async with SessionFactory() as session:
        await ensure_user(session, *_BUYER, UserRole.BUYER.value)
        buyer = (
            await session.execute(select(User).where(User.email == _BUYER[0]))
        ).scalar_one()
        sale = await create_sale(
            session,
            title="X",
            price_minor=1000,
            quantity=1,
            tz_name="UTC",
            starts_at_local=datetime(2026, 6, 1, 11, 0),
            ends_at_local=datetime(2026, 6, 1, 13, 0),
        )
        reservation = await reserve(session, sale.id, buyer.id, now, broadcaster)
        order = await create_order(session, reservation.id, buyer.id, "key", now)
        order_id, buyer_id, sale_id = order.id, buyer.id, sale.id

    async with SessionFactory() as session:
        provider_ref, _ = await start_payment(session, order_id, buyer_id, now)

    # An anonymous stream — what the shop dashboard's connection looks like to
    # the broadcaster as far as this buyer's scoped events are concerned.
    dashboard = broadcaster.subscribe()

    async with SessionFactory() as session:
        await apply_payment_result(session, provider_ref, "approved", now, broadcaster)

    assert ("sale_stats", {"sale_id": sale_id}) in [
        event async for event in _drain(dashboard)
    ]
