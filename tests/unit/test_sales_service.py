from __future__ import annotations

from datetime import UTC, datetime

from app.services.sales import SalePhase, phase, to_utc


def test_phase_upcoming_active_ended() -> None:
    starts = datetime(2026, 1, 1, 13, tzinfo=UTC)
    ends = datetime(2026, 1, 1, 14, tzinfo=UTC)

    assert (
        phase(starts, ends, datetime(2026, 1, 1, 12, tzinfo=UTC)) is SalePhase.UPCOMING
    )
    assert phase(starts, ends, starts) is SalePhase.ACTIVE
    assert phase(starts, ends, ends) is SalePhase.ENDED


def test_to_utc_converts_local_time() -> None:
    # Europe/Moscow is UTC+3.
    utc = to_utc(datetime(2026, 1, 1, 12, 0), "Europe/Moscow")
    assert utc.isoformat() == "2026-01-01T09:00:00+00:00"


def test_to_utc_handles_dst_offset_change() -> None:
    # America/New_York: UTC-5 in winter, UTC-4 in summer.
    winter = to_utc(datetime(2026, 1, 15, 12, 0), "America/New_York")
    assert winter.isoformat() == "2026-01-15T17:00:00+00:00"
    summer = to_utc(datetime(2026, 7, 15, 12, 0), "America/New_York")
    assert summer.isoformat() == "2026-07-15T16:00:00+00:00"
