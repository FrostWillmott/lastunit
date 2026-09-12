from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from app.clock import PostgresClock
from app.config import Settings
from app.db import SessionFactory
from app.models.enums import UserRole
from app.models.sale import Sale
from app.services.auth import ensure_user
from app.services.sales import create_sale

logger = logging.getLogger("app.seed")

# The demo sale the reviewer sees on `make up`: 5 units, 99.00, Europe/Moscow,
# starting a minute after the seed runs. The entrypoint seeds on every container
# start, so creation is idempotent by title and re-anchored — once the previous
# demo sale's window has passed, a fresh one is created so a later start still
# shows a live flash sale rather than a long-ended one. Keying on the title (no
# natural key) is a demo-only simplification; see DECISIONS.md.
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
    """Ensure a live/upcoming demo sale exists, starting a minute from ``now``.

    A demo sale whose window has already passed is left as an ended row and a
    fresh one is created, so re-running the seed never leaves the storefront
    with only a long-ended sale.
    """
    async with SessionFactory() as session:
        # Serialize concurrent seeds (the entrypoint plus a manual `make seed`,
        # or two scaled workers) so the check-then-act can't create two live demo
        # sales; the lock is released when create_sale commits.
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('demo-seed'))")
        )
        live = await session.scalar(
            select(Sale).where(Sale.title == DEMO_SALE_TITLE, Sale.ends_at > now)
        )
        if live is not None:
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
    # The seed runs as its own process (not under uvicorn/create_app), so it
    # must configure the root logger itself or its log lines are dropped.
    logging.basicConfig(level=settings.log_level)
    if settings.app_env == "prod":
        logger.info("skipping the demo seed in prod")
        return
    now = await PostgresClock(SessionFactory).now()
    await seed_shop_user(settings.seed_shop_email, settings.seed_shop_password)
    await seed_demo_sale(now)


if __name__ == "__main__":
    asyncio.run(main())
