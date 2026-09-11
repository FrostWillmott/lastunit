from __future__ import annotations

from sqlalchemy import func, select

from app.db import SessionFactory
from app.models.enums import UserRole
from app.models.user import User
from app.seed import seed_shop_user


async def test_seed_shop_user_is_idempotent() -> None:
    await seed_shop_user("shop@example.com", "secret-password")
    await seed_shop_user("shop@example.com", "secret-password")

    async with SessionFactory() as session:
        user = await session.scalar(
            select(User).where(User.email == "shop@example.com")
        )
        assert user is not None
        assert user.role == UserRole.SHOP.value

        count = await session.scalar(select(func.count()).select_from(User))
        assert count == 1
