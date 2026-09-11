from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import (
    ORDER_STATUS_VALUES,
    PAYMENT_STATUS_VALUES,
    PENDING_PAYMENT_VALUE,
    sql_in_list,
)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({sql_in_list(ORDER_STATUS_VALUES)})", name="status_valid"
        ),
        UniqueConstraint(
            "user_id", "idempotency_key", name="uq_orders_user_idempotency"
        ),
        UniqueConstraint("reservation_id", name="uq_orders_reservation_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("reservations.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str] = mapped_column(String(64))


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({sql_in_list(PAYMENT_STATUS_VALUES)})", name="status_valid"
        ),
        UniqueConstraint("provider_ref", name="uq_payments_provider_ref"),
        # At most one pending attempt per order: a double click violates this
        # before any HTTP call to the stub.
        Index(
            "uq_payments_order_pending",
            "order_id",
            unique=True,
            postgresql_where=text(f"status = {PENDING_PAYMENT_VALUE!r}"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    provider_ref: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
