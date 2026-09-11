from __future__ import annotations

from pathlib import Path

from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]

# Keys that legitimately appear in .env.example without a Settings field:
# docker-compose reads POSTGRES_*, the frontend reads VITE_API_URL. Everything
# else in the file must match a Settings field exactly (config-hygiene: "equals").
NON_SETTINGS_KEYS = frozenset(
    {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "VITE_API_URL"}
)


def _documented_keys() -> set[str]:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    return {
        line.split("=", 1)[0].strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }


def test_env_example_matches_settings() -> None:
    declared = {name.upper() for name in Settings.model_fields}
    documented = _documented_keys()

    extra = documented - NON_SETTINGS_KEYS - declared
    assert not extra, f".env.example keys without a Settings field: {sorted(extra)}"

    missing = declared - documented
    assert not missing, f"Settings fields missing from .env.example: {sorted(missing)}"
