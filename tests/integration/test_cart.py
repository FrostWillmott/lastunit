from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
from sqlalchemy import select

from app.clock import Clock, FrozenClock
from app.db import SessionFactory
from app.main import create_app
from app.models.enums import UserRole
from app.models.user import User
from app.realtime import NoopBroadcaster
from app.services.auth import ensure_user
from app.services.cart import AlreadyInCartError, SoldOutError, reserve
from app.services.sales import create_sale as create_sale_service

_SHOP = ("shop@example.com", "shop-password")
_BUYER = ("buyer@example.com", "buyer-password")


def _client(clock: Clock | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(clock=clock)),
        base_url="http://test",
    )


async def _ensure_user(email: str, password: str, role: str) -> int:
    async with SessionFactory() as session:
        await ensure_user(session, email, password, role)
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        assert user is not None
        return user.id


async def _login(client: httpx.AsyncClient, email: str, password: str) -> None:
    response = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text


async def _create_sale(client: httpx.AsyncClient, starts_at: str, ends_at: str) -> int:
    response = await client.post(
        "/api/sales",
        json={
            "title": "Flash sale",
            "price_minor": 1000,
            "quantity": 5,
            "timezone": "UTC",
            "starts_at": starts_at,
            "ends_at": ends_at,
        },
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


async def test_reserve_before_start_rejected() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    await _ensure_user(*_BUYER, UserRole.BUYER.value)

    async with _client(clock=FrozenClock(now)) as client:
        await _login(client, *_SHOP)
        sale_id = await _create_sale(
            client, "2026-06-01T13:00:00", "2026-06-01T14:00:00"
        )

        await _login(client, *_BUYER)
        response = await client.post(f"/api/sales/{sale_id}/reserve")
        assert response.status_code == 409
        assert response.json()["detail"] == "sale has not started yet"


async def test_reserve_at_start_allowed() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    await _ensure_user(*_BUYER, UserRole.BUYER.value)

    async with _client(clock=FrozenClock(now)) as client:
        await _login(client, *_SHOP)
        # The sale starts exactly at `now`; the boundary is inclusive.
        sale_id = await _create_sale(
            client, "2026-06-01T12:00:00", "2026-06-01T13:00:00"
        )

        await _login(client, *_BUYER)
        response = await client.post(f"/api/sales/{sale_id}/reserve")
        assert response.status_code == 201, response.text


async def test_reserve_holds_a_unit_and_decrements_available() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    await _ensure_user(*_BUYER, UserRole.BUYER.value)

    async with _client(clock=FrozenClock(now)) as client:
        await _login(client, *_SHOP)
        sale_id = await _create_sale(
            client, "2026-06-01T11:00:00", "2026-06-01T13:00:00"
        )

        await _login(client, *_BUYER)
        response = await client.post(f"/api/sales/{sale_id}/reserve")
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "held"

        get = await client.get(f"/api/sales/{sale_id}")
        assert get.json()["available"] == 4


async def test_reserve_same_buyer_twice_is_409() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    await _ensure_user(*_BUYER, UserRole.BUYER.value)

    async with _client(clock=FrozenClock(now)) as client:
        await _login(client, *_SHOP)
        sale_id = await _create_sale(
            client, "2026-06-01T11:00:00", "2026-06-01T13:00:00"
        )

        await _login(client, *_BUYER)
        assert (await client.post(f"/api/sales/{sale_id}/reserve")).status_code == 201
        second = await client.post(f"/api/sales/{sale_id}/reserve")
        assert second.status_code == 409
        assert second.json()["detail"] == "already in cart"


async def test_reserve_same_buyer_concurrent_one_wins() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    async with SessionFactory() as session:
        sale = await create_sale_service(
            session,
            title="Dup",
            price_minor=1000,
            quantity=5,
            tz_name="UTC",
            starts_at_local=datetime(2026, 6, 1, 11, 0),
            ends_at_local=datetime(2026, 6, 1, 13, 0),
        )
        sale_id = sale.id
    buyer = await _ensure_user("dup@example.com", "pw", UserRole.BUYER.value)
    broadcaster = NoopBroadcaster()

    async def try_reserve() -> str:
        async with SessionFactory() as session:
            try:
                await reserve(session, sale_id, buyer, now, broadcaster)
                return "won"
            except AlreadyInCartError:
                return "already in cart"

    results = await asyncio.gather(try_reserve(), try_reserve())
    assert sorted(results) == ["already in cart", "won"]


async def test_reserve_requires_login() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    await _ensure_user(*_SHOP, UserRole.SHOP.value)

    async with _client(clock=FrozenClock(now)) as client:
        await _login(client, *_SHOP)
        sale_id = await _create_sale(
            client, "2026-06-01T11:00:00", "2026-06-01T13:00:00"
        )

    async with _client(clock=FrozenClock(now)) as client:
        response = await client.post(f"/api/sales/{sale_id}/reserve")
        assert response.status_code == 401


async def test_last_unit_two_buyers_one_wins() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    async with SessionFactory() as session:
        sale = await create_sale_service(
            session,
            title="Last one",
            price_minor=1000,
            quantity=1,
            tz_name="UTC",
            starts_at_local=datetime(2026, 6, 1, 11, 0),
            ends_at_local=datetime(2026, 6, 1, 13, 0),
        )
        sale_id = sale.id

    buyer_a = await _ensure_user("a@example.com", "pw-a", UserRole.BUYER.value)
    buyer_b = await _ensure_user("b@example.com", "pw-b", UserRole.BUYER.value)
    broadcaster = NoopBroadcaster()

    async def try_reserve(user_id: int) -> str:
        async with SessionFactory() as session:
            try:
                await reserve(session, sale_id, user_id, now, broadcaster)
                return "won"
            except SoldOutError:
                return "sold out"

    results = await asyncio.gather(try_reserve(buyer_a), try_reserve(buyer_b))
    assert sorted(results) == ["sold out", "won"]


async def test_release_returns_unit_to_shelf() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    await _ensure_user(*_BUYER, UserRole.BUYER.value)

    async with _client(clock=FrozenClock(now)) as client:
        await _login(client, *_SHOP)
        sale_id = await _create_sale(
            client, "2026-06-01T11:00:00", "2026-06-01T13:00:00"
        )

        await _login(client, *_BUYER)
        reserve_resp = await client.post(f"/api/sales/{sale_id}/reserve")
        reservation_id = int(reserve_resp.json()["id"])

        release = await client.delete(f"/api/reservations/{reservation_id}")
        assert release.status_code == 204

        get = await client.get(f"/api/sales/{sale_id}")
        assert get.json()["available"] == 5


async def test_view_cart_lists_held_reservation() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    await _ensure_user(*_BUYER, UserRole.BUYER.value)

    async with _client(clock=FrozenClock(now)) as client:
        await _login(client, *_SHOP)
        sale_id = await _create_sale(
            client, "2026-06-01T11:00:00", "2026-06-01T13:00:00"
        )

        await _login(client, *_BUYER)
        await client.post(f"/api/sales/{sale_id}/reserve")

        cart_resp = await client.get("/api/me/cart")
        assert cart_resp.status_code == 200
        items = cart_resp.json()["items"]
        assert len(items) == 1
        assert items[0]["sale_id"] == sale_id
        assert items[0]["title"] == "Flash sale"


async def test_release_not_found_for_other_buyer() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    await _ensure_user(*_BUYER, UserRole.BUYER.value)
    await _ensure_user("other@example.com", "other-pw", UserRole.BUYER.value)

    async with _client(clock=FrozenClock(now)) as client:
        await _login(client, *_SHOP)
        sale_id = await _create_sale(
            client, "2026-06-01T11:00:00", "2026-06-01T13:00:00"
        )

        await _login(client, *_BUYER)
        reserve_resp = await client.post(f"/api/sales/{sale_id}/reserve")
        reservation_id = int(reserve_resp.json()["id"])

        await _login(client, "other@example.com", "other-pw")
        release = await client.delete(f"/api/reservations/{reservation_id}")
        assert release.status_code == 404
