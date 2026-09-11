from __future__ import annotations

from datetime import UTC, datetime

import httpx
from sqlalchemy import func, select

from app.clock import Clock, FrozenClock
from app.db import SessionFactory
from app.main import create_app
from app.models.enums import OrderStatus, UserRole
from app.models.order import Order
from app.services.auth import ensure_user

_SHOP = ("shop@example.com", "shop-password")
_BUYER = ("buyer@example.com", "buyer-password")


def _client(clock: Clock | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(clock=clock)),
        base_url="http://test",
    )


async def _ensure_user(email: str, password: str, role: str) -> None:
    async with SessionFactory() as session:
        await ensure_user(session, email, password, role)


async def _login(client: httpx.AsyncClient, email: str, password: str) -> None:
    response = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text


async def _reserve(client: httpx.AsyncClient) -> int:
    """Shop creates a sale, the buyer reserves a unit; returns the reservation id."""
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
    assert reserved.status_code == 201, reserved.text
    return int(reserved.json()["id"])


async def test_double_pay_same_key_one_order() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    await _ensure_user(*_BUYER, UserRole.BUYER.value)

    async with _client(clock=FrozenClock(now)) as client:
        reservation_id = await _reserve(client)
        headers = {"Idempotency-Key": "key-1"}

        first = await client.post(
            "/api/orders", json={"reservation_id": reservation_id}, headers=headers
        )
        second = await client.post(
            "/api/orders", json={"reservation_id": reservation_id}, headers=headers
        )
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["amount_minor"] == 1000

    async with SessionFactory() as session:
        count = await session.scalar(select(func.count()).select_from(Order))
        assert count == 1


async def test_create_order_for_released_reservation_is_409() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    await _ensure_user(*_BUYER, UserRole.BUYER.value)

    async with _client(clock=FrozenClock(now)) as client:
        reservation_id = await _reserve(client)
        await client.delete(f"/api/reservations/{reservation_id}")

        response = await client.post(
            "/api/orders",
            json={"reservation_id": reservation_id},
            headers={"Idempotency-Key": "key-2"},
        )
        assert response.status_code == 409


async def test_create_order_for_missing_reservation_404() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    await _ensure_user(*_BUYER, UserRole.BUYER.value)

    async with _client(clock=FrozenClock(now)) as client:
        await _login(client, *_BUYER)
        response = await client.post(
            "/api/orders",
            json={"reservation_id": 999999},
            headers={"Idempotency-Key": "key-4"},
        )
        assert response.status_code == 404


async def test_create_order_same_reservation_different_key_409() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    await _ensure_user(*_BUYER, UserRole.BUYER.value)

    async with _client(clock=FrozenClock(now)) as client:
        reservation_id = await _reserve(client)
        first = await client.post(
            "/api/orders",
            json={"reservation_id": reservation_id},
            headers={"Idempotency-Key": "key-a"},
        )
        assert first.status_code == 201

        second = await client.post(
            "/api/orders",
            json={"reservation_id": reservation_id},
            headers={"Idempotency-Key": "key-b"},
        )
        assert second.status_code == 409


async def test_release_cancels_order() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    await _ensure_user(*_BUYER, UserRole.BUYER.value)

    async with _client(clock=FrozenClock(now)) as client:
        reservation_id = await _reserve(client)
        order = await client.post(
            "/api/orders",
            json={"reservation_id": reservation_id},
            headers={"Idempotency-Key": "key-3"},
        )
        order_id = int(order.json()["id"])

        await client.delete(f"/api/reservations/{reservation_id}")

    async with SessionFactory() as session:
        db_order = await session.scalar(select(Order).where(Order.id == order_id))
        assert db_order is not None
        assert db_order.status == OrderStatus.CANCELLED.value
