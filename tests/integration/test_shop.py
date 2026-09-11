from __future__ import annotations

from datetime import UTC, datetime

import httpx
from sqlalchemy import select

from app.clock import Clock, FrozenClock
from app.db import SessionFactory
from app.main import create_app
from app.models.enums import OrderStatus, UserRole
from app.models.order import Order
from app.paystub_client import PaystubClient
from app.services.auth import ensure_user

_SHOP = ("shop@example.com", "shop-password")
_BUYER = ("buyer@example.com", "buyer-password")


class FakePaystubClient:
    def __init__(
        self, charge_outcome: str = "pending", status: str = "approved"
    ) -> None:
        self.charge_outcome = charge_outcome
        self.status = status
        self.calls: list[str] = []
        self.status_queries: list[str] = []

    async def charge(
        self, reference: str, amount_minor: int, card_number: str, callback_url: str
    ) -> str:
        self.calls.append(reference)
        return self.charge_outcome

    async def get_status(self, reference: str) -> str:
        self.status_queries.append(reference)
        return self.status


def _client(paystub: PaystubClient, clock: Clock | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=create_app(clock=clock, paystub_client=paystub)
        ),
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


def _sale_payload() -> dict[str, object]:
    return {
        "title": "Flash sale",
        "price_minor": 1000,
        "quantity": 5,
        "timezone": "UTC",
        "starts_at": "2026-06-01T11:00:00",
        "ends_at": "2026-06-01T13:00:00",
    }


async def test_shop_stats_counts() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    paystub = FakePaystubClient(charge_outcome="approved")
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    await _ensure_user(*_BUYER, UserRole.BUYER.value)

    async with _client(paystub, clock=FrozenClock(now)) as client:
        await _login(client, *_SHOP)
        sale = await client.post("/api/sales", json=_sale_payload())
        sale_id = int(sale.json()["id"])

        await _login(client, *_BUYER)
        reserved = await client.post(f"/api/sales/{sale_id}/reserve")
        reservation_id = int(reserved.json()["id"])

        # While the hold is live, the dashboard counts it as in-cart.
        await _login(client, *_SHOP)
        mid = await client.get(f"/api/shop/sales/{sale_id}/stats")
        assert mid.json()["in_cart"] == 1
        assert mid.json()["available"] == 4

        await _login(client, *_BUYER)
        order = await client.post(
            "/api/orders",
            json={"reservation_id": reservation_id},
            headers={"Idempotency-Key": "k1"},
        )
        order_id = int(order.json()["id"])
        paid = await client.post(
            f"/api/orders/{order_id}/pay", json={"card_number": "4111111111110000"}
        )
        assert paid.json()["status"] == "approved"

        await _login(client, *_SHOP)
        stats = await client.get(f"/api/shop/sales/{sale_id}/stats")
        assert stats.status_code == 200
        body = stats.json()
        assert body["available"] == 4
        assert body["sold"] == 1
        assert body["in_cart"] == 0
        assert body["revenue_minor"] == 1000


async def test_me_orders_lists_orders() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    paystub = FakePaystubClient(charge_outcome="pending")
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    await _ensure_user(*_BUYER, UserRole.BUYER.value)

    async with _client(paystub, clock=FrozenClock(now)) as client:
        await _login(client, *_SHOP)
        sale = await client.post("/api/sales", json=_sale_payload())
        sale_id = int(sale.json()["id"])

        await _login(client, *_BUYER)
        reserved = await client.post(f"/api/sales/{sale_id}/reserve")
        reservation_id = int(reserved.json()["id"])
        order = await client.post(
            "/api/orders",
            json={"reservation_id": reservation_id},
            headers={"Idempotency-Key": "k1"},
        )
        order_id = int(order.json()["id"])

        orders = await client.get("/api/me/orders")
        assert orders.status_code == 200
        body = orders.json()
        assert len(body) == 1
        assert body[0]["id"] == order_id
        assert body[0]["status"] == "pending"


async def test_check_status_applies_result_like_webhook() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    paystub = FakePaystubClient(charge_outcome="pending", status="approved")
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    await _ensure_user(*_BUYER, UserRole.BUYER.value)

    async with _client(paystub, clock=FrozenClock(now)) as client:
        await _login(client, *_SHOP)
        sale = await client.post("/api/sales", json=_sale_payload())
        sale_id = int(sale.json()["id"])

        await _login(client, *_BUYER)
        reserved = await client.post(f"/api/sales/{sale_id}/reserve")
        reservation_id = int(reserved.json()["id"])
        order = await client.post(
            "/api/orders",
            json={"reservation_id": reservation_id},
            headers={"Idempotency-Key": "k1"},
        )
        order_id = int(order.json()["id"])
        paid = await client.post(
            f"/api/orders/{order_id}/pay", json={"card_number": "4111111111119995"}
        )
        assert paid.json()["status"] == "pending"

        reference = paystub.calls[0]
        await _login(client, *_SHOP)
        check = await client.post(f"/api/shop/payments/{reference}/check")
        assert check.json()["status"] == "approved"

    async with SessionFactory() as session:
        order = await session.scalar(select(Order).where(Order.id == order_id))
        assert order is not None and order.status == OrderStatus.PAID.value
