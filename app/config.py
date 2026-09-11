from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """The single place the backend reads its environment.

    Values come from the process environment (docker-compose injects ``.env``
    via ``env_file``); nothing here reads a file itself. Unknown variables are
    ignored by default.
    """

    app_env: Literal["dev", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    # Compose derives the real value from POSTGRES_* and CI sets it directly;
    # this default is only the fallback for running outside compose (local
    # pytest), and matches the CI db service's app:app convention.
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app"
    session_ttl_days: int = 30
    # Demo shop account the seed creates; the reviewer logs into the shop screen
    # with these (not a production secret).
    seed_shop_email: str = "shop@example.com"
    seed_shop_password: str = "shop-password"  # noqa: S105  (demo credential, not a secret)
