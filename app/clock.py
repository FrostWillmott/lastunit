from __future__ import annotations

from datetime import datetime
from typing import Protocol, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class Clock(Protocol):
    async def now(self) -> datetime:
        """Return the current time (UTC)."""


class PostgresClock:
    """Production clock: reads ``now()`` from Postgres, the single time source."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def now(self) -> datetime:
        async with self._session_factory() as session:
            result = await session.execute(text("SELECT now()"))
            return cast(datetime, result.scalar_one())


class FrozenClock:
    """Test clock returning a fixed instant (testing.md's ``frozen_clock``)."""

    def __init__(self, current: datetime) -> None:
        self._current = current

    async def now(self) -> datetime:
        return self._current
