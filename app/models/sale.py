from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import SaleStatus


class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (
        CheckConstraint("available >= 0", name="ck_sales_available_nonnegative"),
        CheckConstraint("starts_at < ends_at", name="ck_sales_start_before_end"),
        Index("ix_sales_status_ends_at", "status", "ends_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    price_minor: Mapped[int] = mapped_column(BigInteger)
    quantity: Mapped[int] = mapped_column(Integer)
    available: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default=SaleStatus.ACTIVE.value)
