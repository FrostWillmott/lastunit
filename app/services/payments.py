from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OrderStatus, PaymentStatus, ReservationStatus
from app.models.order import Order, Payment
from app.models.reservation import Reservation
from app.models.sale import Sale
from app.models.user import User
from app.realtime import Broadcaster, NoopBroadcaster
from app.services import notifications


class OrderNotFoundError(Exception):
    pass


class PaymentAlreadyPendingError(Exception):
    pass


class HoldExpiredError(Exception):
    pass


class ReservationNotHeldError(Exception):
    pass


async def start_payment(
    db: AsyncSession,
    order_id: int,
    user_id: int,
    now: datetime,
) -> tuple[str, int]:
    """Begin a payment attempt: ``held -> paying`` + INSERT a pending attempt.

    Returns ``(provider_ref, amount_minor)``. The reservation stays the buyer's
    until the stub answers; the order stays ``pending``.
    """
    order = (
        await db.execute(
            select(Order).where(Order.id == order_id, Order.user_id == user_id)
        )
    ).scalar_one_or_none()
    if order is None:
        raise OrderNotFoundError
    reservation = (
        await db.execute(
            select(Reservation).where(Reservation.id == order.reservation_id)
        )
    ).scalar_one_or_none()
    sale = (
        await db.execute(select(Sale).where(Sale.id == order.sale_id))
    ).scalar_one_or_none()
    if reservation is None or sale is None:
        raise OrderNotFoundError

    # Guarded transition: the hold must still be live and the sale open.
    sale_ends_at = (
        select(Sale.ends_at).where(Sale.id == reservation.sale_id).scalar_subquery()
    )
    result = await db.execute(
        update(Reservation)
        .where(
            Reservation.id == reservation.id,
            Reservation.status == ReservationStatus.HELD.value,
            Reservation.expires_at > now,
            now < sale_ends_at,
        )
        .values(status=ReservationStatus.PAYING.value)
        .returning(Reservation.id)
    )
    if result.scalar_one_or_none() is None:
        if (
            reservation.status == ReservationStatus.EXPIRED.value
            or reservation.expires_at <= now
        ):
            raise HoldExpiredError
        if reservation.status == ReservationStatus.PAYING.value:
            raise PaymentAlreadyPendingError
        raise ReservationNotHeldError  # sold / released / cleared

    provider_ref = secrets.token_urlsafe(16)
    db.add(
        Payment(
            order_id=order_id,
            provider_ref=provider_ref,
            status=PaymentStatus.PENDING.value,
            requested_at=now,
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise PaymentAlreadyPendingError from None
    return provider_ref, order.amount_minor


async def apply_payment_result(
    db: AsyncSession,
    provider_ref: str,
    outcome: str,
    now: datetime,
    broadcaster: Broadcaster | None = None,
) -> None:
    """Apply an approved/declined result; idempotent via the pending guard."""
    broadcaster = broadcaster or NoopBroadcaster()
    result = await db.execute(
        update(Payment)
        .where(
            Payment.provider_ref == provider_ref,
            Payment.status == PaymentStatus.PENDING.value,
        )
        .values(status=outcome, resolved_at=now)
        .returning(Payment.order_id)
    )
    order_id = result.scalar_one_or_none()
    if order_id is None:
        return  # already resolved, or an unknown reference

    order = (
        await db.execute(select(Order).where(Order.id == order_id))
    ).scalar_one_or_none()
    if order is None:
        return

    new_order_status: str
    if outcome == PaymentStatus.APPROVED.value:
        await db.execute(
            update(Order)
            .where(Order.id == order_id, Order.status == OrderStatus.PENDING.value)
            .values(status=OrderStatus.PAID.value)
        )
        await db.execute(
            update(Reservation)
            .where(
                Reservation.id == order.reservation_id,
                Reservation.status == ReservationStatus.PAYING.value,
            )
            .values(status=ReservationStatus.SOLD.value)
        )
        # Outbox: one email per order, written in the same transaction.
        buyer = (
            await db.execute(select(User).where(User.id == order.user_id))
        ).scalar_one_or_none()
        await notifications.enqueue_order_paid(
            db, order_id, buyer.email if buyer else "", order.amount_minor
        )
        new_order_status = OrderStatus.PAID.value
    else:  # declined — return to the cart (or clear if the sale already ended).
        sale = (
            await db.execute(select(Sale).where(Sale.id == order.sale_id))
        ).scalar_one_or_none()
        new_status = (
            ReservationStatus.CLEARED.value
            if (sale is not None and sale.ends_at <= now)
            else ReservationStatus.HELD.value
        )
        await db.execute(
            update(Reservation)
            .where(
                Reservation.id == order.reservation_id,
                Reservation.status == ReservationStatus.PAYING.value,
            )
            .values(status=new_status)
        )
        if new_status == ReservationStatus.CLEARED.value:
            # The sale has ended and the reservation is cleared, so the order can
            # never be paid again — cancel it instead of leaving it stuck pending.
            await db.execute(
                update(Order)
                .where(
                    Order.id == order_id,
                    Order.status == OrderStatus.PENDING.value,
                )
                .values(status=OrderStatus.CANCELLED.value)
            )
            new_order_status = OrderStatus.CANCELLED.value
        else:
            new_order_status = OrderStatus.PENDING.value
    await db.commit()
    await broadcaster.publish(
        "order_status", {"order_id": order_id, "status": new_order_status}
    )
