from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db import SessionFactory
from app.models.enums import ReservationStatus, UserRole
from app.models.reservation import Reservation
from app.models.sale import Sale
from app.models.user import User
from app.realtime import NoopBroadcaster
from app.scheduler import run_once
from app.services.auth import ensure_user
from app.services.cart import reserve
from app.services.sales import create_sale


async def _reserve_unit(sale_id: int, now: datetime) -> None:
    async with SessionFactory() as session:
        await ensure_user(session, "buyer@example.com", "pw", UserRole.BUYER.value)
        user = (
            await session.execute(select(User).where(User.email == "buyer@example.com"))
        ).scalar_one()
        await reserve(session, sale_id, user.id, now, NoopBroadcaster())


async def test_hold_expires_returns_stock() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    async with SessionFactory() as session:
        sale = await create_sale(
            session,
            title="Last one",
            price_minor=1000,
            quantity=1,
            tz_name="UTC",
            starts_at_local=datetime(2026, 6, 1, 11, 0),
            ends_at_local=datetime(2026, 6, 1, 13, 0),
        )
        sale_id = sale.id
    await _reserve_unit(sale_id, now)

    async with SessionFactory() as session:
        expired = await run_once(session, now + timedelta(minutes=11))
        assert expired == 1

    async with SessionFactory() as session:
        refreshed = await session.scalar(select(Sale).where(Sale.id == sale_id))
        assert refreshed is not None and refreshed.available == 1
        reservation = await session.scalar(
            select(Reservation).where(Reservation.sale_id == sale_id)
        )
        assert reservation is not None
        assert reservation.status == ReservationStatus.EXPIRED.value


async def test_run_once_leaves_live_hold_alone() -> None:
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    async with SessionFactory() as session:
        sale = await create_sale(
            session,
            title="Live",
            price_minor=1000,
            quantity=1,
            tz_name="UTC",
            starts_at_local=datetime(2026, 6, 1, 11, 0),
            ends_at_local=datetime(2026, 6, 1, 13, 0),
        )
        sale_id = sale.id
    await _reserve_unit(sale_id, now)

    async with SessionFactory() as session:
        expired = await run_once(session, now + timedelta(minutes=5))
        assert expired == 0

    async with SessionFactory() as session:
        reservation = await session.scalar(
            select(Reservation).where(Reservation.sale_id == sale_id)
        )
        assert reservation is not None
        assert reservation.status == ReservationStatus.HELD.value
