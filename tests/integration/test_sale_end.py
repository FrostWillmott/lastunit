from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.db import SessionFactory
from app.models.enums import OrderStatus, ReservationStatus, SaleStatus, UserRole
from app.models.notification import Notification
from app.models.order import Order
from app.models.reservation import Reservation
from app.models.sale import Sale
from app.models.user import User
from app.realtime import NoopBroadcaster
from app.scheduler import end_ended_sales
from app.services.auth import ensure_user
from app.services.cart import reserve
from app.services.notifications import CART_CLEARED
from app.services.orders import create_order
from app.services.payments import start_payment
from app.services.sales import create_sale


async def test_sale_end_clears_holds_and_notifies() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)

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
        sale_id = sale.id
        reservation = await reserve(session, sale.id, buyer.id, now, NoopBroadcaster())
        await create_order(session, reservation.id, buyer.id, "key-1", now)

    # The sale ends at 13:00; run the cleanup at 13:01.
    async with SessionFactory() as session:
        ended = await end_ended_sales(session, now + timedelta(minutes=61))
        assert ended == 1

    async with SessionFactory() as session:
        refreshed_sale = await session.scalar(select(Sale).where(Sale.id == sale_id))
        assert refreshed_sale is not None
        assert refreshed_sale.status == SaleStatus.ENDED.value
        assert refreshed_sale.available == 0
        refreshed_reservation = await session.scalar(
            select(Reservation).where(Reservation.sale_id == sale_id)
        )
        assert refreshed_reservation is not None
        assert refreshed_reservation.status == ReservationStatus.CLEARED.value
        order = (
            await session.execute(
                select(Order).where(Order.reservation_id == refreshed_reservation.id)
            )
        ).scalar_one()
        assert order.status == OrderStatus.CANCELLED.value
        notification = (
            await session.execute(
                select(Notification).where(Notification.kind == CART_CLEARED)
            )
        ).scalar_one()
        assert notification.entity_id == refreshed_reservation.id


async def test_sale_end_leaves_paying_reservation() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)

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
        reservation = await reserve(session, sale.id, buyer.id, now, NoopBroadcaster())
        order = await create_order(session, reservation.id, buyer.id, "key-1", now)
        order_id = order.id
        reservation_id = reservation.id

    # Start a payment so the reservation is paying.
    async with SessionFactory() as session:
        await start_payment(session, order_id, buyer.id, now)

    async with SessionFactory() as session:
        await end_ended_sales(session, now + timedelta(minutes=61))

    async with SessionFactory() as session:
        refreshed_reservation = await session.scalar(
            select(Reservation).where(Reservation.id == reservation_id)
        )
        assert refreshed_reservation is not None
        assert refreshed_reservation.status == ReservationStatus.PAYING.value
        notifications_count = await session.scalar(
            select(func.count()).select_from(Notification)
        )
        assert notifications_count == 0
