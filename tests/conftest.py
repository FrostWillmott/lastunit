from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class _ComposeEnv(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = "app"
    postgres_password: str = "app"
    postgres_db: str = "app"


def _test_database_url() -> str:
    if url := os.environ.get("DATABASE_URL"):
        return url
    env = _ComposeEnv()
    # A separate database so the per-test TRUNCATE never touches the developer's
    # `make up` data; CI sets DATABASE_URL to an ephemeral database instead.
    return (
        f"postgresql+asyncpg://{env.postgres_user}:{env.postgres_password}"
        f"@localhost:5432/{env.postgres_db}_test"
    )


# Set DATABASE_URL before any test imports app.db, so the engine always points
# at the test database (never the developer's default). Both the unit and
# integration suites import this conftest.
os.environ.setdefault("DATABASE_URL", _test_database_url())
