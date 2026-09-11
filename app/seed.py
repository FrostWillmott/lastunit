from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.config import Settings
from app.db import SessionFactory
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth import hash_password


async def seed_shop_user(email: str, password: str) -> None:
    """Create the shop user if it does not exist yet (idempotent)."""
    async with SessionFactory() as session:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing is None:
            session.add(
                User(
                    email=email,
                    password_hash=hash_password(password),
                    role=UserRole.SHOP.value,
                )
            )
            await session.commit()


async def main() -> None:
    settings = Settings()
    await seed_shop_user(settings.seed_shop_email, settings.seed_shop_password)


if __name__ == "__main__":
    asyncio.run(main())
