from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime

import httpx
from sqlalchemy import select

from app.clock import Clock, FrozenClock
from app.config import Settings
from app.db import SessionFactory
from app.main import create_app
from app.models.enums import OrderStatus, PaymentStatus, ReservationStatus, UserRole
from app.models.order import Order, Payment
from app.models.reservation import Reservation
from app.models.sale import Sale
from app.paystub_client import PaystubClient
from app.services.auth import ensure_user

_SHOP = ("shop@example.com", "shop-password")
_BUYER = ("buyer@example.com", "buyer-password")


class FakePaystubClient:
    def __init__(self, outcome: str = "pending") -> None:
        self.outcome = outcome
        self.calls: list[dict[str, object]] = []

    async def charge(
        self, reference: str, amount_minor: int, card_number: str, callback_url: str
    ) -> str:
        self.calls.append(
            {
                "reference": reference,
                "amount_minor": amount_minor,
                "card_number": card_number,
                "callback_url": callback_url,
            }
        )
        return self.outcome

    async def get_status(self, reference: str) -> str:
        return self.outcome


class TimeoutPaystubClient:
    async def charge(
        self, reference: str, amount_minor: int, card_number: str, callback_url: str
    ) -> str:
        raise httpx.ConnectTimeout("timed out")

    async def get_status(self, reference: str) -> str:
        return "pending"


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


async def _place_order(client: httpx.AsyncClient) -> int:
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
    reservation_id = int(reserved.json()["id"])
    order = await client.post(
        "/api/orders",
        json={"reservation_id": reservation_id},
        headers={"Idempotency-Key": "pay-key"},
    )
    return int(order.json()["id"])


async def _setup(paystub: PaystubClient) -> tuple[httpx.AsyncClient, datetime]:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    await _ensure_user(*_SHOP, UserRole.SHOP.value)
    await _ensure_user(*_BUYER, UserRole.BUYER.value)
    client = _client(paystub, clock=FrozenClock(now))
    return client, now


async def _webhook(
    client: httpx.AsyncClient, reference: str, status: str
) -> httpx.Response:
    body = json.dumps({"reference": reference, "status": status}).encode()
    signature = hmac.new(
        Settings().paystub_webhook_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return await client.post(
        "/api/payments/webhook",
        content=body,
        headers={"X-Webhook-Signature": signature, "Content-Type": "application/json"},
    )


async def test_double_pay_calls_paystub_once() -> None:
    paystub = FakePaystubClient("pending")
    client, _ = await _setup(paystub)
    async with client:
        order_id = await _place_order(client)

        async def pay() -> httpx.Response:
            return await client.post(
                f"/api/orders/{order_id}/pay",
                json={"card_number": "4111111111119995"},
            )

        first, second = await asyncio.gather(pay(), pay())
        assert {first.status_code, second.status_code} == {200, 409}
        loser = first if first.status_code == 409 else second
        assert loser.json()["detail"] == "payment already in progress"

    assert len(paystub.calls) == 1


async def test_declined_attempt_returns_reservation_to_cart() -> None:
    paystub = FakePaystubClient("declined")
    client, _ = await _setup(paystub)
    async with client:
        order_id = await _place_order(client)
        response = await client.post(
            f"/api/orders/{order_id}/pay", json={"card_number": "4111111111110002"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "declined"

    async with SessionFactory() as session:
        reservation = (
            (await session.execute(select(Reservation).where(Reservation.user_id != 0)))
            .scalars()
            .first()
        )
        assert reservation is not None
        assert reservation.status == ReservationStatus.HELD.value
        order = await session.scalar(select(Order).where(Order.id == order_id))
        assert order is not None
        assert order.status == OrderStatus.PENDING.value


async def test_hung_payment_keeps_stock() -> None:
    paystub = FakePaystubClient("pending")
    client, _ = await _setup(paystub)
    async with client:
        order_id = await _place_order(client)
        response = await client.post(
            f"/api/orders/{order_id}/pay", json={"card_number": "4111111111119995"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "pending"

    async with SessionFactory() as session:
        payment = (
            await session.execute(select(Payment).where(Payment.order_id == order_id))
        ).scalar_one()
        assert payment.status == PaymentStatus.PENDING.value
        # The reserved unit stays off the shelf: the reservation is paying and
        # the sale's available is one less than its quantity, not returned.
        order = await session.scalar(select(Order).where(Order.id == order_id))
        assert order is not None
        reservation = await session.scalar(
            select(Reservation).where(Reservation.id == order.reservation_id)
        )
        sale = await session.scalar(select(Sale).where(Sale.id == order.sale_id))
        assert reservation is not None
        assert reservation.status == ReservationStatus.PAYING.value
        assert sale is not None
        assert sale.available == sale.quantity - 1


async def test_hung_payment_resolves_via_webhook() -> None:
    paystub = FakePaystubClient("pending")
    client, _ = await _setup(paystub)
    async with client:
        order_id = await _place_order(client)
        await client.post(
            f"/api/orders/{order_id}/pay", json={"card_number": "4111111111119995"}
        )

        reference = str(paystub.calls[0]["reference"])
        response = await _webhook(client, reference, "approved")
        assert response.status_code == 200

    async with SessionFactory() as session:
        order = await session.scalar(select(Order).where(Order.id == order_id))
        assert order is not None
        assert order.status == OrderStatus.PAID.value
        payment = (
            await session.execute(select(Payment).where(Payment.order_id == order_id))
        ).scalar_one()
        assert payment.status == PaymentStatus.APPROVED.value


async def test_paystub_timeout_keeps_order_pending() -> None:
    paystub = TimeoutPaystubClient()
    client, _ = await _setup(paystub)
    async with client:
        order_id = await _place_order(client)
        response = await client.post(
            f"/api/orders/{order_id}/pay", json={"card_number": "4111111111110000"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "pending"

    async with SessionFactory() as session:
        order = await session.scalar(select(Order).where(Order.id == order_id))
        assert order is not None
        assert order.status == OrderStatus.PENDING.value


async def test_webhook_rejects_malformed_payloads() -> None:
    paystub = FakePaystubClient("pending")
    client, _ = await _setup(paystub)

    def sign(body: bytes) -> str:
        return hmac.new(
            Settings().paystub_webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()

    async with client:
        for body in (
            b"\xff\xff\xff",  # not valid UTF-8 / not JSON
            b'{"reference": 123, "status": "approved"}',
            b'{"reference": null, "status": "approved"}',
            b'{"reference": "r", "status": "wat"}',
        ):
            response = await client.post(
                "/api/payments/webhook",
                content=body,
                headers={"X-Webhook-Signature": sign(body)},
            )
            assert response.status_code == 400, body


async def test_webhook_rejects_non_ascii_signature() -> None:
    paystub = FakePaystubClient("pending")
    client, _ = await _setup(paystub)

    async with client:
        body = json.dumps({"reference": "r", "status": "approved"}).encode()
        # Send the signature as raw latin-1 bytes (as a real client would); the
        # server must treat it as a bad signature, not a 500.
        response = await client.post(
            "/api/payments/webhook",
            content=body,
            headers={b"X-Webhook-Signature": "café".encode("latin-1")},
        )
        assert response.status_code == 401
