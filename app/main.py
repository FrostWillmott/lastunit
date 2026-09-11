from __future__ import annotations

import logging

from fastapi import FastAPI

from app.config import Settings
from app.routers import health


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app with its settings injected for testability."""
    settings = settings or Settings()
    logging.basicConfig(level=settings.log_level)

    expose_docs = settings.app_env != "prod"
    app = FastAPI(
        title="lastunit",
        docs_url="/docs" if expose_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if expose_docs else None,
    )
    app.include_router(health.router, prefix="/api")
    return app
