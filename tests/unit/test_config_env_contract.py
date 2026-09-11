from __future__ import annotations

from pathlib import Path

from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def _documented_keys() -> set[str]:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    return {
        line.split("=", 1)[0].strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }


def test_every_setting_is_documented_in_env_example() -> None:
    """No declared setting is missing from ``.env.example``.

    The reverse does not hold: ``.env.example`` also carries docker-compose
    variables (``POSTGRES_*``), which are not ``Settings`` fields.
    """
    declared = {name.upper() for name in Settings.model_fields}
    missing = declared - _documented_keys()
    assert not missing, f"Settings fields missing from .env.example: {sorted(missing)}"
