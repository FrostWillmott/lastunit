from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OrderStatus, ReservationStatus
from app.models.order import Order
from app.models.reservation import Reservation
from app.models.sale import Sale


class ReservationNotFoundError(Exception):
    pass


class ReservationNotHeldError(Exception):
    pass


class ReservationAlreadyOrderedError(Exception):
    pass


async def list_user_orders(db: AsyncSession, user_id: int) -> list[Order]:
    return list(
        (
            await db.scalars(
                select(Order).where(Order.user_id == user_id).order_by(Order.id)
            )
        ).all()
    )


async def create_order(
    db: AsyncSession,
    reservation_id: int,
    user_id: int,
    idempotency_key: str,
    now: datetime,
) -> Order:
    # Idempotency: a repeated key returns the order it created, no second row.
    existing = (
        await db.execute(
            select(Order).where(
                Order.user_id == user_id,
                Order.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    reservation = await db.scalar(
        select(Reservation).where(
            Reservation.id == reservation_id,
            Reservation.user_id == user_id,
        )
    )
    if reservation is None:
        raise ReservationNotFoundError
    if (
        reservation.status != ReservationStatus.HELD.value
        or reservation.expires_at <= now
    ):
        raise ReservationNotHeldError

    sale = await db.scalar(select(Sale).where(Sale.id == reservation.sale_id))
    if sale is None:
        raise ReservationNotFoundError

    order = Order(
        reservation_id=reservation_id,
        user_id=user_id,
        sale_id=reservation.sale_id,
        amount_minor=sale.price_minor,
        status=OrderStatus.PENDING.value,
        idempotency_key=idempotency_key,
    )
    db.add(order)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # A concurrent duplicate of the same key — return the row that won.
        existing = (
            await db.execute(
                select(Order).where(
                    Order.user_id == user_id,
                    Order.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        raise ReservationAlreadyOrderedError from None
    return order
