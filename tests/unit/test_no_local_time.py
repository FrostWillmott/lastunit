from __future__ import annotations

from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2] / "app"

# Time must come from the injected Clock (SELECT now()), never from the local
# machine or from now() baked into SQL. Any of these in app/ is a bug.
FORBIDDEN = ("datetime.now", "func.now", "now()")


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
