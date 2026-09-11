from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OrderStatus, PaymentStatus, ReservationStatus
from app.models.order import Order, Payment
from app.models.reservation import Reservation
from app.models.sale import Sale


@dataclass
class SaleStats:
    available: int
    sold: int
    in_cart: int
    revenue_minor: int
    pending_payments: list[Payment]


async def sale_stats(db: AsyncSession, sale_id: int) -> SaleStats | None:
    sale = await db.scalar(select(Sale).where(Sale.id == sale_id))
    if sale is None:
        return None

    sold = await db.scalar(
        select(func.count())
        .select_from(Reservation)
        .where(
            Reservation.sale_id == sale_id,
            Reservation.status == ReservationStatus.SOLD.value,
        )
    )
    in_cart = await db.scalar(
        select(func.count())
        .select_from(Reservation)
        .where(
            Reservation.sale_id == sale_id,
            Reservation.status.in_(
                [ReservationStatus.HELD.value, ReservationStatus.PAYING.value]
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
