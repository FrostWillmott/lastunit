from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReservationStatus
from app.models.reservation import Reservation
from app.models.sale import Sale
from app.realtime import Broadcaster

HOLD_MINUTES = 10


class SaleNotFoundError(Exception):
    pass


class NotStartedError(Exception):
    pass


class SaleEndedError(Exception):
    pass


class SoldOutError(Exception):
    pass


class AlreadyInCartError(Exception):
    pass


async def reserve(
    db: AsyncSession,
    sale_id: int,
    user_id: int,
    now: datetime,
    broadcaster: Broadcaster,
) -> Reservation:
    # Pre-check: one active hold per buyer per sale (partial UNIQUE is the
    # backstop for a concurrent double-click).
    existing = await db.scalar(
        select(Reservation).where(
            Reservation.sale_id == sale_id,
            Reservation.user_id == user_id,
            Reservation.status.in_(
                [ReservationStatus.HELD.value, ReservationStatus.PAYING.value]
            ),
        )
    )
    if existing is not None:
        raise AlreadyInCartError

    # Take one unit atomically, only while the sale is live and in stock.
    result = await db.execute(
        update(Sale)
        .where(
            Sale.id == sale_id,
            Sale.available > 0,
            Sale.starts_at <= now,
            now < Sale.ends_at,
        )
        .values(available=Sale.available - 1)
        .returning(Sale.available)
    )
    new_available = result.scalar_one_or_none()
    if new_available is None:
        sale = (
            await db.execute(select(Sale).where(Sale.id == sale_id))
        ).scalar_one_or_none()
        if sale is None:
            raise SaleNotFoundError
        if now < sale.starts_at:
            raise NotStartedError
        if sale.ends_at <= now:
            raise SaleEndedError
        raise SoldOutError

    reservation = Reservation(
        sale_id=sale_id,
        user_id=user_id,
        status=ReservationStatus.HELD.value,
        expires_at=now + timedelta(minutes=HOLD_MINUTES),
    )
    db.add(reservation)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise AlreadyInCartError from None

    await broadcaster.publish(
        "stock_changed", {"sale_id": sale_id, "available": new_available}
    )
    return reservation
