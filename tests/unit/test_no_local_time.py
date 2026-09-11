from __future__ import annotations

from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2] / "app"

# Time must come from the injected Clock, never from the local machine or from
# now() baked into a SQL expression. The bare `now()` is deliberately NOT listed:
# the Clock implements `SELECT now()` (raw Postgres), the one sanctioned source,
# so matching it here would flag the very code the guard protects.
FORBIDDEN = (
    "datetime.now",  # local machine time
    "datetime.utcnow",  # local machine time (deprecated)
    "func.now",  # SQLAlchemy now() inside an expression
    "time.time",  # local machine clock
    "date.today",  # local machine date
)


def test_app_uses_no_local_or_sql_time_source() -> None:
    offenders: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(pattern in line for pattern in FORBIDDEN):
                offenders.append(f"{path}:{lineno}: {line.strip()}")

    assert not offenders, (
        "time must come from the injected Clock, not local/SQL time:\n"
        + "\n".join(offenders)
    )
