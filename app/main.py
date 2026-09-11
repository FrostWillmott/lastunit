from __future__ import annotations

import logging

from fastapi import FastAPI

from app.clock import Clock, PostgresClock
from app.config import Settings
from app.db import SessionFactory
from app.realtime import Broadcaster, NoopBroadcaster
from app.routers import auth, health, sales


def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
    broadcaster: Broadcaster | None = None,
) -> FastAPI:
    """Build the app with its settings, clock and broadcaster injected for tests."""
    settings = settings or Settings()
    clock = clock or PostgresClock(SessionFactory)
    broadcaster = broadcaster or NoopBroadcaster()
    # App loggers (``app.*``) follow LOG_LEVEL; the process entry (uvicorn) owns
    # the root handlers, so set the app logger instead of reconfiguring root.
    logging.getLogger("app").setLevel(settings.log_level)

    expose_docs = settings.app_env != "prod"
    app = FastAPI(
        title="lastunit",
        docs_url="/docs" if expose_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if expose_docs else None,
    )
    app.state.settings = settings
    app.state.clock = clock
    app.state.broadcaster = broadcaster
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(sales.router, prefix="/api")
    return app


# The ASGI entry point the Dockerfile's `uvicorn app.main:app` imports.
app = create_app()
