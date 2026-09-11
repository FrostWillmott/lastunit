from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.db import SessionFactory
from app.models.enums import UserRole
from app.models.notification import Notification
from app.models.user import User
from app.realtime import NoopBroadcaster
from app.services.auth import ensure_user
from app.services.cart import reserve
from app.services.notifications import ORDER_PAID, send_pending
from app.services.orders import create_order
from app.services.payments import apply_payment_result, start_payment
from app.services.sales import create_sale


async def test_order_email_sent_exactly_once() -> None:
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

    # Pay approved — the outbox gains one email in the same transaction.
    async with SessionFactory() as session:
        provider_ref, _ = await start_payment(session, order_id, buyer.id, now)
        await apply_payment_result(session, provider_ref, "approved", now)

    async with SessionFactory() as session:
        count = await session.scalar(select(func.count()).select_from(Notification))
        assert count == 1
        notification = (await session.execute(select(Notification))).scalar_one()
        assert notification.kind == ORDER_PAID
        assert notification.entity_id == order_id
        assert notification.sent_at is None

    # A duplicate webhook does not enqueue a second email.
    async with SessionFactory() as session:
        await apply_payment_result(session, provider_ref, "approved", now)
    async with SessionFactory() as session:
        count = await session.scalar(select(func.count()).select_from(Notification))
        assert count == 1

    # The sender marks it sent.
    async with SessionFactory() as session:
        sent = await send_pending(session, now)
        assert sent == 1
    async with SessionFactory() as session:
        notification = (await session.execute(select(Notification))).scalar_one()
        assert notification.sent_at is not None
