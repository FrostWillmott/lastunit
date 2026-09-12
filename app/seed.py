from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.clock import PostgresClock
from app.config import Settings
from app.db import SessionFactory
from app.models.enums import UserRole
from app.models.sale import Sale
from app.services.auth import ensure_user
from app.services.sales import create_sale

logger = logging.getLogger("app.seed")

# The demo sale the reviewer sees on first `make up`: starts a minute after the
# seed runs, 5 units, a half-hour window, priced 99.00 in the shop's zone. The
# entrypoint runs the seed on every container start, so creation is idempotent
# by title — re-seeding must not pile up demo sales.
DEMO_SALE_TITLE = "Demo flash sale"
DEMO_SALE_TIMEZONE = "Europe/Moscow"
DEMO_SALE_PRICE_MINOR = 9900
DEMO_SALE_QUANTITY = 5
DEMO_SALE_START_IN = timedelta(minutes=1)
DEMO_SALE_DURATION = timedelta(minutes=30)


async def seed_shop_user(email: str, password: str) -> None:
    """Create or reconcile the shop user (idempotent)."""
    async with SessionFactory() as session:
        await ensure_user(session, email, password, UserRole.SHOP.value)


async def seed_demo_sale(now: datetime) -> None:
    """Create the demo sale if none exists, starting a minute from ``now``."""
    async with SessionFactory() as session:
        existing = await session.scalar(
            select(Sale).where(Sale.title == DEMO_SALE_TITLE)
        )
        if existing is not None:
            return
        start_local = (
            now.astimezone(ZoneInfo(DEMO_SALE_TIMEZONE)).replace(tzinfo=None)
            + DEMO_SALE_START_IN
        )
        await create_sale(
            session,
            title=DEMO_SALE_TITLE,
            price_minor=DEMO_SALE_PRICE_MINOR,
            quantity=DEMO_SALE_QUANTITY,
            tz_name=DEMO_SALE_TIMEZONE,
            starts_at_local=start_local,
            ends_at_local=start_local + DEMO_SALE_DURATION,
        )
        logger.info("seeded demo sale %r", DEMO_SALE_TITLE)


async def main() -> None:
    settings = Settings()
    if settings.app_env == "prod":
        logger.info("skipping the demo seed in prod")
        return
    now = await PostgresClock(SessionFactory).now()
    await seed_shop_user(settings.seed_shop_email, settings.seed_shop_password)
    await seed_demo_sale(now)


if __name__ == "__main__":
    asyncio.run(main())
