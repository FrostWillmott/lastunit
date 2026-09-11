from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic.config import Config
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command

ROOT = Path(__file__).resolve().parents[2]


class _ComposeEnv(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = "app"
    postgres_password: str = "app"
    postgres_db: str = "app"


def _test_database_url() -> str:
    if url := os.environ.get("DATABASE_URL"):
        return url
    env = _ComposeEnv()
    return (
        f"postgresql+asyncpg://{env.postgres_user}:{env.postgres_password}"
        f"@localhost:5432/{env.postgres_db}"
    )


# Fix the test DATABASE_URL before importing the app, so app.db's engine points
# at the test database (never the developer's default).
os.environ.setdefault("DATABASE_URL", _test_database_url())

from app.db import SessionFactory  # noqa: E402  (env must be set first)


@pytest.fixture(scope="session", autouse=True)
def _migrate_database() -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
async def _truncate_tables() -> AsyncIterator[None]:
    # Each test gets a clean database: TRUNCATE every table in the public schema
    # (alembic_version excepted). Real commits — race tests need separate
    # connections, so a rollback-per-test session would not work.
    async with SessionFactory() as session:
        result = await session.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        )
        tables = [str(row) for row in result.scalars()]
        if tables:
            await session.execute(
                text(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE")
            )
        await session.commit()
    yield


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
