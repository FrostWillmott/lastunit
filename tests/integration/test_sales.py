from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.clock import Clock, FrozenClock
from app.db import SessionFactory
from app.main import create_app
from app.models.enums import UserRole
from app.services.auth import ensure_user

_SHOP = ("shop@example.com", "shop-password")


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


def _payload() -> dict[str, object]:
    return {
        "title": "Flash sale",
        "price_minor": 1000,
        "quantity": 5,
        "timezone": "UTC",
        "starts_at": "2026-06-01T12:00:00",
        "ends_at": "2026-06-01T13:00:00",
    }


async def test_create_sale_as_shop() -> None:
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    async with _client() as client:
        await _login(client, *_SHOP)
        response = await client.post("/api/sales", json=_payload())
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["title"] == "Flash sale"
        assert body["available"] == 5
        assert datetime.fromisoformat(body["starts_at"]) == datetime(
            2026, 6, 1, 12, tzinfo=UTC
        )


async def test_create_sale_requires_shop_role() -> None:
    await _ensure_user("buyer@example.com", "buyer-password", UserRole.BUYER.value)
    async with _client() as client:
        await _login(client, "buyer@example.com", "buyer-password")
        response = await client.post("/api/sales", json=_payload())
        assert response.status_code == 403


async def test_get_sale_reports_phase_and_server_now() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    async with _client(clock=FrozenClock(now)) as client:
        await _login(client, *_SHOP)
        create = await client.post(
            "/api/sales",
            json={
                "title": "Soon",
                "price_minor": 1000,
                "quantity": 5,
                "timezone": "UTC",
                "starts_at": "2026-06-01T13:00:00",
                "ends_at": "2026-06-01T14:00:00",
            },
        )
        sale_id = create.json()["id"]

        get = await client.get(f"/api/sales/{sale_id}")
        body = get.json()
        assert body["phase"] == "upcoming"
        assert datetime.fromisoformat(body["server_now"]) == now


async def test_list_sales() -> None:
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    async with _client() as client:
        await _login(client, *_SHOP)
        await client.post("/api/sales", json=_payload())
        response = await client.get("/api/sales")
        assert response.status_code == 200
        assert len(response.json()) == 1


async def test_create_sale_rejects_negative_price() -> None:
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    async with _client() as client:
        await _login(client, *_SHOP)
        payload = _payload()
        payload["price_minor"] = -5000
        response = await client.post("/api/sales", json=payload)
        assert response.status_code == 422


async def test_create_sale_rejects_offset_aware_time() -> None:
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    async with _client() as client:
        await _login(client, *_SHOP)
        payload = _payload()
        payload["ends_at"] = "2026-06-01T13:00:00Z"
        response = await client.post("/api/sales", json=payload)
        assert response.status_code == 422


async def test_create_sale_rejects_dst_collapsed_window() -> None:
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    async with _client() as client:
        await _login(client, *_SHOP)
        response = await client.post(
            "/api/sales",
            json={
                "title": "DST gap",
                "price_minor": 1000,
                "quantity": 5,
                "timezone": "Europe/Berlin",
                "starts_at": "2026-03-29T02:30:00",
                "ends_at": "2026-03-29T03:30:00",
            },
        )
        assert response.status_code == 422
