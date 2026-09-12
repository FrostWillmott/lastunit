from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pytest import MonkeyPatch
from sqlalchemy import func, select

from app import seed
from app.db import SessionFactory
from app.models.enums import UserRole
from app.models.sale import Sale
from app.models.user import User
from app.seed import (
    DEMO_SALE_DURATION,
    DEMO_SALE_QUANTITY,
    DEMO_SALE_START_IN,
    DEMO_SALE_TITLE,
    seed_demo_sale,
    seed_shop_user,
)
from app.services.auth import register, verify_password


async def test_seed_shop_user_is_idempotent_and_normalizes_email() -> None:
    await seed_shop_user("Shop@Example.com ", "secret-password")
    await seed_shop_user("shop@example.com", "secret-password")

    async with SessionFactory() as session:
        user = await session.scalar(
            select(User).where(User.email == "shop@example.com")
        )
        assert user is not None
        assert user.role == UserRole.SHOP.value
        assert verify_password("secret-password", user.password_hash)

        count = await session.scalar(select(func.count()).select_from(User))
        assert count == 1


async def test_seed_upgrades_an_existing_buyer_to_shop() -> None:
    async with SessionFactory() as session:
        await register(session, "shop@example.com", "buyer-password")

    await seed_shop_user("shop@example.com", "shop-password")

    async with SessionFactory() as session:
        user = await session.scalar(
            select(User).where(User.email == "shop@example.com")
        )
        assert user is not None
        assert user.role == UserRole.SHOP.value
        assert verify_password("shop-password", user.password_hash)


async def test_main_seeds_from_settings(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("SEED_SHOP_EMAIL", "main-shop@example.com")
    monkeypatch.setenv("SEED_SHOP_PASSWORD", "main-password")

    await seed.main()

    async with SessionFactory() as session:
        user = await session.scalar(
            select(User).where(User.email == "main-shop@example.com")
        )
        assert user is not None
        assert user.role == UserRole.SHOP.value


async def test_main_skips_seed_in_prod(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SEED_SHOP_EMAIL", "prod-shop@example.com")
    monkeypatch.setenv("SEED_SHOP_PASSWORD", "prod-password")

    await seed.main()

    async with SessionFactory() as session:
        user_count = await session.scalar(select(func.count()).select_from(User))
        sale_count = await session.scalar(select(func.count()).select_from(Sale))
        assert user_count == 0
        assert sale_count == 0


async def test_seed_demo_sale_creates_when_none() -> None:
    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    await seed_demo_sale(now)

    async with SessionFactory() as session:
        sale = await session.scalar(select(Sale))
    assert sale is not None
    assert sale.title == DEMO_SALE_TITLE
    assert sale.quantity == DEMO_SALE_QUANTITY
    assert sale.available == DEMO_SALE_QUANTITY
    assert sale.starts_at == now + DEMO_SALE_START_IN


async def test_seed_demo_sale_is_noop_while_live() -> None:
    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    await seed_demo_sale(now)
    await seed_demo_sale(now + DEMO_SALE_DURATION / 2)

    async with SessionFactory() as session:
        count = await session.scalar(select(func.count()).select_from(Sale))
    assert count == 1


async def test_seed_demo_sale_reanchors_after_end() -> None:
    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    await seed_demo_sale(now)
    after_end = now + DEMO_SALE_START_IN + DEMO_SALE_DURATION + timedelta(minutes=1)
    await seed_demo_sale(after_end)

    async with SessionFactory() as session:
        sales = list((await session.scalars(select(Sale).order_by(Sale.id))).all())
    assert len(sales) == 2
    assert sales[1].starts_at == after_end + DEMO_SALE_START_IN
