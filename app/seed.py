from __future__ import annotations

import asyncio
import logging

from app.config import Settings
from app.db import SessionFactory
from app.models.enums import UserRole
from app.services.auth import ensure_user

logger = logging.getLogger("app.seed")


async def seed_shop_user(email: str, password: str) -> None:
    """Create or reconcile the shop user (idempotent)."""
    async with SessionFactory() as session:
        await ensure_user(session, email, password, UserRole.SHOP.value)


async def main() -> None:
    settings = Settings()
    if settings.app_env == "prod":
        logger.info("skipping the demo shop seed in prod")
        return
    await seed_shop_user(settings.seed_shop_email, settings.seed_shop_password)


if __name__ == "__main__":
    asyncio.run(main())
