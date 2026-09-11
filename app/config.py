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
