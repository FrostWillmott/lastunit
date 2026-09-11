from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db import SessionFactory
from app.models.enums import OrderStatus, ReservationStatus, UserRole
from app.models.order import Order
from app.models.reservation import Reservation
from app.models.user import User
from app.realtime import NoopBroadcaster
from app.scheduler import run_once
from app.services.auth import ensure_user
from app.services.cart import reserve
from app.services.orders import create_order
from app.services.payments import apply_payment_result, start_payment
from app.services.sales import create_sale


async def test_payment_started_before_expiry_completes_after() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)

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
        order = await create_order(session, reservation.id, buyer.id, "key-5")
        order_id = order.id

    # Pay at T+9 (the hold expires at T+10); the stub hangs.
    async with SessionFactory() as session:
        provider_ref, _ = await start_payment(
            session, order_id, buyer.id, now + timedelta(minutes=9)
        )

    # The scheduler runs after the hold's original expiry — the paying
    # reservation is not expired, so its unit stays off the shelf.
    async with SessionFactory() as session:
        expired = await run_once(session, now + timedelta(minutes=11))
        assert expired == 0

    # The stub settles later.
    async with SessionFactory() as session:
        await apply_payment_result(
            session, provider_ref, "approved", now + timedelta(minutes=12)
        )

    async with SessionFactory() as session:
        refreshed_order = await session.scalar(
            select(Order).where(Order.id == order_id)
        )
        assert refreshed_order is not None
        assert refreshed_order.status == OrderStatus.PAID.value
        refreshed_reservation = await session.scalar(
            select(Reservation).where(Reservation.sale_id == sale.id)
        )
        assert refreshed_reservation is not None
        assert refreshed_reservation.status == ReservationStatus.SOLD.value
