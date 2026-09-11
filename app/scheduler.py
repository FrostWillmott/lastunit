from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.models.enums import OrderStatus, ReservationStatus, SaleStatus
from app.models.order import Order
from app.models.reservation import Reservation
from app.models.sale import Sale
from app.models.user import User
from app.realtime import Broadcaster, NoopBroadcaster
from app.services import notifications

logger = logging.getLogger("app.scheduler")


async def run_once(
    session: AsyncSession,
    now: datetime,
    broadcaster: Broadcaster | None = None,
) -> int:
    """Expire every lapsed hold, return its unit, cancel its order.

    ``FOR UPDATE SKIP LOCKED`` lets several workers run this without double-firing
    the same hold. Returns the number of holds expired.
    """
    broadcaster = broadcaster or NoopBroadcaster()
    result = await session.execute(
        select(Reservation)
        .where(
            Reservation.status == ReservationStatus.HELD.value,
            Reservation.expires_at <= now,
        )
        .with_for_update(skip_locked=True)
    )
    lapsed = list(result.scalars().all())
    sale_ids = {reservation.sale_id for reservation in lapsed}
    for reservation in lapsed:
        reservation.status = ReservationStatus.EXPIRED.value
        await session.execute(
            update(Sale)
            .where(Sale.id == reservation.sale_id)
            .values(available=Sale.available + 1)
        )
        await session.execute(
            update(Order)
            .where(
                Order.reservation_id == reservation.id,
                Order.status == OrderStatus.PENDING.value,
            )
            .values(status=OrderStatus.CANCELLED.value)
        )
    await session.commit()
    for sale_id in sale_ids:
        await broadcaster.publish("stock_changed", {"sale_id": sale_id})
    return len(lapsed)


async def end_ended_sales(
    session: AsyncSession,
    now: datetime,
    broadcaster: Broadcaster | None = None,
) -> int:
    """Mark ended sales, clear their held reservations, notify their owners.

    ``paying`` reservations are left alone (they settle later). Returns the
    number of sales ended.
    """
    broadcaster = broadcaster or NoopBroadcaster()
    result = await session.execute(
        select(Sale)
        .where(Sale.ends_at <= now, Sale.status == SaleStatus.ACTIVE.value)
        .with_for_update(skip_locked=True)
    )
    ended = list(result.scalars().all())
    for sale in ended:
        sale.status = SaleStatus.ENDED.value
        sale.available = 0
        held = await session.execute(
            select(Reservation).where(
                Reservation.sale_id == sale.id,
                Reservation.status == ReservationStatus.HELD.value,
            )
        )
        for reservation in held.scalars().all():
            reservation.status = ReservationStatus.CLEARED.value
            await session.execute(
                update(Order)
                .where(
                    Order.reservation_id == reservation.id,
                    Order.status == OrderStatus.PENDING.value,
                )
                .values(status=OrderStatus.CANCELLED.value)
            )
            buyer = (
                await session.execute(
                    select(User).where(User.id == reservation.user_id)
                )
            ).scalar_one_or_none()
            await notifications.enqueue_cart_cleared(
                session, reservation.id, buyer.email if buyer else ""
            )
    await session.commit()
    for sale in ended:
        await broadcaster.publish(
            "sale_status", {"sale_id": sale.id, "status": SaleStatus.ENDED.value}
        )
    return len(ended)


async def loop(
    clock: Clock,
    session_factory: async_sessionmaker[AsyncSession],
    broadcaster: Broadcaster,
    interval: float = 1.0,
) -> None:
    """Poll forever. On the first tick it processes whatever came due while the
    server was down (fire-late), so a missed hold expiry still returns the unit."""
    while True:
        try:
            async with session_factory() as session:
                now = await clock.now()
                expired = await run_once(session, now, broadcaster)
                ended = await end_ended_sales(session, now, broadcaster)
                sent = await notifications.send_pending(session, now)
                if expired or ended or sent:
                    logger.info(
                        "expired %d holds, ended %d sales, sent %d notifications",
                        expired,
                        ended,
                        sent,
                    )
        except Exception:  # a bad tick must not kill the loop
            logger.exception("scheduler tick failed")
        await asyncio.sleep(interval)
