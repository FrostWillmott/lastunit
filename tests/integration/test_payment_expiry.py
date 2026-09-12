from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from app.db import SessionFactory
from app.models.enums import OrderStatus, ReservationStatus, UserRole
from app.models.notification import Notification
from app.models.order import Order
from app.models.reservation import Reservation
from app.models.sale import Sale
from app.models.user import User
from app.realtime import NoopBroadcaster
from app.scheduler import run_once
from app.services.auth import ensure_user
from app.services.cart import list_cart, reserve
from app.services.notifications import CART_CLEARED
from app.services.orders import create_order
from app.services.payments import (
    HoldExpiredError,
    apply_payment_result,
    start_payment,
)
from app.services.sales import create_sale


async def _place_order(now: datetime) -> tuple[int, int, int]:
    """Create a buyer, a one-unit sale, a held reservation and an order."""
    async with SessionFactory() as session:
        await ensure_user(session, "buyer@example.com", "pw", UserRole.BUYER.value)
        buyer = (
            await session.execute(select(User).where(User.email == "buyer@example.com"))
        ).scalar_one()
        sale = await create_sale(
            session,
            title="Last one",
            price_minor=1000,
            quantity=1,
            tz_name="UTC",
            starts_at_local=datetime(2026, 6, 1, 11, 0),
            ends_at_local=datetime(2026, 6, 1, 13, 0),
        )
        reservation = await reserve(session, sale.id, buyer.id, now, NoopBroadcaster())
        order = await create_order(session, reservation.id, buyer.id, "key", now)
        return sale.id, buyer.id, order.id


async def test_payment_started_before_expiry_completes_after() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    sale_id, buyer_id, order_id = await _place_order(now)

    # Pay at T+9 (the hold expires at T+10); the stub hangs.
    async with SessionFactory() as session:
        provider_ref, _ = await start_payment(
            session, order_id, buyer_id, now + timedelta(minutes=9)
        )

    # The sweep runs after the hold's original expiry — the paying reservation
    # is not expired, so the unit stays off the shelf and stays paying.
    async with SessionFactory() as session:
        expired = await run_once(session, now + timedelta(minutes=11))
        assert expired == 0

        sale = await session.scalar(select(Sale).where(Sale.id == sale_id))
        assert sale is not None and sale.available == 0
        reservation = await session.scalar(
            select(Reservation).where(Reservation.sale_id == sale_id)
        )
        assert reservation is not None
        assert reservation.status == ReservationStatus.PAYING.value

    # The stub settles later (the HTTP webhook path is covered in test_payments).
    async with SessionFactory() as session:
        await apply_payment_result(
            session, provider_ref, "approved", now + timedelta(minutes=12)
        )

    async with SessionFactory() as session:
        order = await session.scalar(select(Order).where(Order.id == order_id))
        assert order is not None and order.status == OrderStatus.PAID.value
        reservation = await session.scalar(
            select(Reservation).where(Reservation.sale_id == sale_id)
        )
        assert reservation is not None
        assert reservation.status == ReservationStatus.SOLD.value


async def test_pay_on_expired_hold_is_409() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    _, buyer_id, order_id = await _place_order(now)

    async with SessionFactory() as session:
        with pytest.raises(HoldExpiredError):
            await start_payment(
                session, order_id, buyer_id, now + timedelta(minutes=11)
            )


async def test_approved_after_order_cancelled_does_not_email() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    _, buyer_id, order_id = await _place_order(now)

    async with SessionFactory() as session:
        provider_ref, _ = await start_payment(session, order_id, buyer_id, now)

    # A concurrent sale-end sweep cancels the order and clears the reservation
    # while the payment is still pending. Simulate that committed state directly
    # (the guarded-clear transition is what makes it possible to survive).
    async with SessionFactory() as session:
        reservation_id = (
            await session.execute(
                select(Order.reservation_id).where(Order.id == order_id)
            )
        ).scalar_one()
        await session.execute(
            update(Order)
            .where(Order.id == order_id)
            .values(status=OrderStatus.CANCELLED.value)
        )
        await session.execute(
            update(Reservation)
            .where(Reservation.id == reservation_id)
            .values(status=ReservationStatus.CLEARED.value)
        )
        await session.commit()

    async with SessionFactory() as session:
        await apply_payment_result(session, provider_ref, "approved", now)

    async with SessionFactory() as session:
        order = await session.scalar(select(Order).where(Order.id == order_id))
        assert order is not None
        assert order.status == OrderStatus.CANCELLED.value
        reservation = await session.scalar(
            select(Reservation).where(Reservation.id == reservation_id)
        )
        assert reservation is not None
        assert reservation.status == ReservationStatus.CLEARED.value
        count = await session.scalar(select(func.count()).select_from(Notification))
        assert count == 0


async def test_declined_after_sale_end_notifies_cart_cleared() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    _, buyer_id, order_id = await _place_order(now)

    async with SessionFactory() as session:
        provider_ref, _ = await start_payment(session, order_id, buyer_id, now)

    # The stub declines after the sale has ended (13:00); the reservation is
    # cleared and its owner notified, mirroring the sale-end cleanup path.
    async with SessionFactory() as session:
        await apply_payment_result(
            session, provider_ref, "declined", now + timedelta(minutes=61)
        )

    async with SessionFactory() as session:
        order = await session.scalar(select(Order).where(Order.id == order_id))
        assert order is not None
        assert order.status == OrderStatus.CANCELLED.value
        notification = await session.scalar(
            select(Notification).where(Notification.kind == CART_CLEARED)
        )
        assert notification is not None
        assert notification.entity_id == order.reservation_id


async def test_list_cart_includes_paying_reservation() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    _, buyer_id, order_id = await _place_order(now)

    async with SessionFactory() as session:
        await start_payment(session, order_id, buyer_id, now)

    # The hold has lapsed, but the reservation is paying (a hung stub) — it must
    # still appear in the cart so the buyer sees their unit is still held.
    async with SessionFactory() as session:
        items = await list_cart(session, buyer_id, now + timedelta(minutes=11))

    assert len(items) == 1
    assert items[0][0].status == ReservationStatus.PAYING.value
