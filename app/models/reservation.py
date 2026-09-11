from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import (
    ACTIVE_RESERVATION_VALUES,
    RESERVATION_STATUS_VALUES,
    sql_in_list,
)


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({sql_in_list(RESERVATION_STATUS_VALUES)})", name="status_valid"
        ),
        Index("ix_reservations_status_expires_at", "status", "expires_at"),
        # One active reservation per buyer per sale: the database enforces it,
        # not an application check.
        Index(
            "uq_reservations_sale_user_active",
            "sale_id",
            "user_id",
            unique=True,
            postgresql_where=text(
                f"status IN ({sql_in_list(ACTIVE_RESERVATION_VALUES)})"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
