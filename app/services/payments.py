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
        # Re-read the reservation: the in-memory object still says ``held``, but a
        # concurrent payment may have already flipped it, and the loser should be
        # told "payment already in progress", not "reservation is not held".
        # ``populate_existing`` is what makes the re-read real: this session's
        # identity map already holds the stale instance, so a plain select()
        # returns that and discards the committed row it just fetched.
        current = (
            await db.execute(
                select(Reservation)
                .where(Reservation.id == reservation.id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        if (
            current.status == ReservationStatus.EXPIRED.value
            or current.expires_at <= now
        ):
            raise HoldExpiredError
        if current.status == ReservationStatus.PAYING.value:
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
        paid = (
            await db.execute(
                update(Order)
                .where(Order.id == order_id, Order.status == OrderStatus.PENDING.value)
                .values(status=OrderStatus.PAID.value)
                .returning(Order.id)
            )
        ).scalar_one_or_none()
        if paid is None:
            # The order was already settled (cancelled) while this payment was
            # pending. The stub charged the buyer, but we must not email "paid"
            # or sell a reservation that is no longer paying — report the order's
            # real status instead.
            current = await db.scalar(select(Order.status).where(Order.id == order_id))
            new_order_status = current if current is not None else order.status
        else:
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
            # never be paid again — cancel it and notify the owner, mirroring the
            # sale-end cleanup path.
            await db.execute(
                update(Order)
                .where(
                    Order.id == order_id,
                    Order.status == OrderStatus.PENDING.value,
                )
                .values(status=OrderStatus.CANCELLED.value)
            )
            buyer = (
                await db.execute(select(User).where(User.id == order.user_id))
            ).scalar_one_or_none()
            await notifications.enqueue_cart_cleared(
                db, order.reservation_id, buyer.email if buyer else ""
            )
            new_order_status = OrderStatus.CANCELLED.value
        else:
            new_order_status = OrderStatus.PENDING.value
    await db.commit()
    await broadcaster.publish(
        "order_status",
        {"order_id": order_id, "status": new_order_status},
        user_id=order.user_id,
    )
