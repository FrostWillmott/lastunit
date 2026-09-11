from __future__ import annotations

from pytest import MonkeyPatch
from sqlalchemy import func, select

from app import seed
from app.db import SessionFactory
from app.models.enums import UserRole
from app.models.user import User
from app.seed import seed_shop_user
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
        count = await session.scalar(select(func.count()).select_from(User))
        assert count == 0
