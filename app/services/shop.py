from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OrderStatus, PaymentStatus, ReservationStatus
from app.models.order import Order, Payment
from app.models.reservation import Reservation
from app.models.sale import Sale


class SaleNotFoundError(Exception):
    pass


@dataclass
class SaleStats:
    available: int
    sold: int
    in_cart: int
    revenue_minor: int
    pending_payments: list[Payment]


async def sale_stats(db: AsyncSession, sale_id: int, now: datetime) -> SaleStats:
    sale = await db.scalar(select(Sale).where(Sale.id == sale_id))
    if sale is None:
        raise SaleNotFoundError

    sold = await db.scalar(
        select(func.count())
        .select_from(Reservation)
        .where(
            Reservation.sale_id == sale_id,
            Reservation.status == ReservationStatus.SOLD.value,
        )
    )
    # In-cart is a paying reservation, or a held one whose hold has not lapsed.
    in_cart = await db.scalar(
        select(func.count())
        .select_from(Reservation)
        .where(
            Reservation.sale_id == sale_id,
            or_(
                Reservation.status == ReservationStatus.PAYING.value,
                and_(
                    Reservation.status == ReservationStatus.HELD.value,
                    Reservation.expires_at > now,
                ),
            ),
        )
    )
    revenue = await db.scalar(
        select(func.coalesce(func.sum(Order.amount_minor), 0)).where(
            Order.sale_id == sale_id,
            Order.status == OrderStatus.PAID.value,
        )
    )
    pending = list(
        (
            await db.scalars(
                select(Payment)
                .join(Order, Order.id == Payment.order_id)
                .where(
                    Order.sale_id == sale_id,
                    Payment.status == PaymentStatus.PENDING.value,
                )
            )
        ).all()
    )
    return SaleStats(
        available=sale.available,
        sold=sold or 0,
        in_cart=in_cart or 0,
        revenue_minor=revenue or 0,
        pending_payments=pending,
    )
