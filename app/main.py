from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import scheduler
from app.clock import Clock, PostgresClock
from app.config import Settings
from app.db import SessionFactory
from app.paystub_client import HttpPaystubClient, PaystubClient
from app.realtime import Broadcaster, InProcessBroadcaster
from app.routers import auth, cart, events, health, orders, payments, sales, shop


def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
    broadcaster: Broadcaster | None = None,
    paystub_client: PaystubClient | None = None,
    scheduler_interval: float = 1.0,
) -> FastAPI:
    """Build the app with its settings, clock and broadcaster injected for tests."""
    settings = settings or Settings()
    clock = clock or PostgresClock(SessionFactory)
    broadcaster = broadcaster or InProcessBroadcaster()
    paystub_client = paystub_client or HttpPaystubClient(settings.paystub_url)
    # App loggers (``app.*``) follow LOG_LEVEL. uvicorn configures only its own
    # ``uvicorn.*`` loggers and leaves the root logger without a handler, so an
    # ``app.*`` INFO line falls through to Python's ``lastResort`` (WARNING+)
    # and never appears. Configure the root handler once so the email stub and
    # the scheduler are observable; ``basicConfig`` is a no-op if a handler
    # already exists (e.g. the seed's own process already called it).
    logging.basicConfig(level=settings.log_level)
    logging.getLogger("app").setLevel(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(
            scheduler.loop(clock, SessionFactory, broadcaster, scheduler_interval)
        )
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    expose_docs = settings.app_env != "prod"
    app = FastAPI(
        title="lastunit",
        docs_url="/docs" if expose_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if expose_docs else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.clock = clock
    app.state.broadcaster = broadcaster
    app.state.paystub = paystub_client
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(sales.router, prefix="/api")
    app.include_router(cart.router, prefix="/api")
    app.include_router(orders.router, prefix="/api")
    app.include_router(payments.router, prefix="/api")
    app.include_router(shop.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    return app


# The ASGI entry point the Dockerfile's `uvicorn app.main:app` imports.
app = create_app()
