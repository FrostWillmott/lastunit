from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command

ROOT = Path(__file__).resolve().parents[2]

# Resolved by the root conftest (tests/conftest.py), which sets DATABASE_URL
# before any test imports app.db.
TEST_DATABASE_URL = os.environ["DATABASE_URL"]


async def _ensure_database_exists() -> None:
    db_name = TEST_DATABASE_URL.rsplit("/", 1)[-1]
    admin_url = f"{TEST_DATABASE_URL.rsplit('/', 1)[0]}/postgres"
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": db_name},
            )
            if result.scalar() is None:
                await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        await engine.dispose()


from app.db import SessionFactory, engine  # noqa: E402  (env must be set first)


@pytest.fixture(scope="session", autouse=True)
def _migrate_database() -> None:
    asyncio.run(_ensure_database_exists())
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


@pytest.fixture(autouse=True)
async def _dispose_engine() -> AsyncIterator[None]:
    # asyncpg connections are bound to the event loop they were created in; each
    # async test runs in a fresh loop, so close the pool after every test or the
    # next loop reuses a connection from a dead loop.
    yield
    await engine.dispose()


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
