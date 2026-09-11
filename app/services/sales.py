from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SaleStatus
from app.models.sale import Sale


class SalePhase(StrEnum):
    UPCOMING = "upcoming"
    ACTIVE = "active"
    ENDED = "ended"


class InvalidSaleWindowError(Exception):
    """The sale's window collapses to a non-positive UTC range after zone conversion."""


def to_utc(local: datetime, tz_name: str) -> datetime:
    """Interpret a naive wall-clock time in the given IANA zone and return UTC."""
    return local.replace(tzinfo=ZoneInfo(tz_name)).astimezone(UTC)


def phase(starts_at: datetime, ends_at: datetime, now: datetime) -> SalePhase:
    """Derive the sale's display phase from its window and the current time."""
    if now < starts_at:
        return SalePhase.UPCOMING
    if now < ends_at:
        return SalePhase.ACTIVE
    return SalePhase.ENDED


async def create_sale(
    db: AsyncSession,
    title: str,
    price_minor: int,
    quantity: int,
    tz_name: str,
    starts_at_local: datetime,
    ends_at_local: datetime,
) -> Sale:
    starts_utc = to_utc(starts_at_local, tz_name)
    ends_utc = to_utc(ends_at_local, tz_name)
    if ends_utc <= starts_utc:
        raise InvalidSaleWindowError
    sale = Sale(
        title=title,
        price_minor=price_minor,
        quantity=quantity,
        available=quantity,
        starts_at=starts_utc,
        ends_at=ends_utc,
        timezone=tz_name,
        status=SaleStatus.ACTIVE.value,
    )
    db.add(sale)
    await db.commit()
    return sale


async def list_sales(db: AsyncSession) -> list[Sale]:
    return list((await db.scalars(select(Sale).order_by(Sale.starts_at))).all())


async def get_sale(db: AsyncSession, sale_id: int) -> Sale | None:
    result = await db.execute(select(Sale).where(Sale.id == sale_id))
    return result.scalar_one_or_none()
