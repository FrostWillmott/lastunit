from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ACTIVE_RESERVATION_VALUES, ReservationStatus
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


class ReservationNotFoundError(Exception):
    pass


class NotHeldError(Exception):
    pass


async def _expire_lapsed_hold(
    db: AsyncSession, sale_id: int, user_id: int, now: datetime
) -> None:
    """Return the buyer's lapsed hold on this sale to the shelf (lazy expiry).

    The scheduler sweeps every lapsed hold on a timer (commit 13); this on-demand
    path lets a buyer re-buy the same sale the moment their hold expires.
    """
    result = await db.execute(
        update(Reservation)
        .where(
            Reservation.sale_id == sale_id,
            Reservation.user_id == user_id,
            Reservation.status == ReservationStatus.HELD.value,
            Reservation.expires_at <= now,
        )
        .values(status=ReservationStatus.EXPIRED.value)
        .returning(Reservation.id)
    )
    lapsed = list(result.scalars().all())
    if lapsed:
        await db.execute(
            update(Sale)
            .where(Sale.id == sale_id)
            .values(available=Sale.available + len(lapsed))
        )


async def reserve(
    db: AsyncSession,
    sale_id: int,
    user_id: int,
    now: datetime,
    broadcaster: Broadcaster,
) -> Reservation:
    await _expire_lapsed_hold(db, sale_id, user_id, now)

    # Pre-check: one active hold per buyer per sale (partial UNIQUE is the
    # backstop for a concurrent double-click).
    existing = await db.scalar(
        select(Reservation).where(
            Reservation.sale_id == sale_id,
            Reservation.user_id == user_id,
            Reservation.status.in_(ACTIVE_RESERVATION_VALUES),
            Reservation.expires_at > now,
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
        .returning(Sale.available, Sale.ends_at)
    )
    row = result.first()
    if row is None:
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
    new_available, sale_ends_at = row
    expires_at = min(now + timedelta(minutes=HOLD_MINUTES), sale_ends_at)

    reservation = Reservation(
        sale_id=sale_id,
        user_id=user_id,
        status=ReservationStatus.HELD.value,
        expires_at=expires_at,
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


async def release(
    db: AsyncSession,
    reservation_id: int,
    user_id: int,
    now: datetime,
    broadcaster: Broadcaster,
) -> None:
    """Release a held reservation and return its unit to the shelf."""
    result = await db.execute(
        update(Reservation)
        .where(
            Reservation.id == reservation_id,
            Reservation.user_id == user_id,
            Reservation.status == ReservationStatus.HELD.value,
            Reservation.expires_at > now,
        )
        .values(status=ReservationStatus.RELEASED.value, released_at=now)
        .returning(Reservation.sale_id)
    )
    sale_id = result.scalar_one_or_none()
    if sale_id is None:
        reservation = (
            await db.execute(
                select(Reservation).where(Reservation.id == reservation_id)
            )
        ).scalar_one_or_none()
        if reservation is None or reservation.user_id != user_id:
            raise ReservationNotFoundError
        raise NotHeldError

    result = await db.execute(
        update(Sale)
        .where(Sale.id == sale_id)
        .values(available=Sale.available + 1)
        .returning(Sale.available)
    )
    new_available = result.scalar_one()
    await db.commit()
    await broadcaster.publish(
        "stock_changed", {"sale_id": sale_id, "available": new_available}
    )


async def list_cart(
    db: AsyncSession, user_id: int, now: datetime
) -> list[tuple[Reservation, Sale]]:
    result = await db.execute(
        select(Reservation, Sale)
        .join(Sale, Sale.id == Reservation.sale_id)
        .where(
            Reservation.user_id == user_id,
            Reservation.status == ReservationStatus.HELD.value,
            Reservation.expires_at > now,
        )
        .order_by(Reservation.expires_at)
    )
    return list(result.tuples().all())
