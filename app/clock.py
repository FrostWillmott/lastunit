from __future__ import annotations

from datetime import datetime
from typing import Protocol, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class Clock(Protocol):
    async def now(self, session: AsyncSession | None = None) -> datetime:
        """Return the current time (UTC), reading through ``session`` when given."""


class PostgresClock:
    """Production clock: reads ``now()`` from Postgres, the single time source.

    When a session is supplied, the read reuses that session's connection, so a
    request never holds two pooled connections at once (the request's own
    uncommitted transaction plus a second one for the clock); otherwise it opens
    a fresh session, which is what the seed and the scheduler do.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def now(self, session: AsyncSession | None = None) -> datetime:
        if session is not None:
            result = await session.execute(text("SELECT now()"))
            return cast(datetime, result.scalar_one())
        async with self._session_factory() as own:
            result = await own.execute(text("SELECT now()"))
            return cast(datetime, result.scalar_one())


class FrozenClock:
    """Test clock returning a fixed instant (testing.md's ``frozen_clock``)."""

    def __init__(self, current: datetime) -> None:
        self._current = current

    async def now(self, session: AsyncSession | None = None) -> datetime:
        return self._current
