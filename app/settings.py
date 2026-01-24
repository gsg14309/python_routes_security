from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    App settings.

    Notes:
    - Keep defaults *local* and deterministic for a demo project.
    - Allow overriding via env vars to support integration into an existing system.
    """

    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore")

    db_url: str | None = None
    security_config_path: str | None = None
    log_level: str = "INFO"

    def resolved_db_url(self) -> str:
        if self.db_url:
            return self.db_url

        repo_root = Path(__file__).resolve().parents[1]
        db_path = repo_root / "app.db"
        return f"sqlite:///{db_path}"

    def resolved_security_config_path(self) -> Path:
        if self.security_config_path:
            return Path(self.security_config_path)

        repo_root = Path(__file__).resolve().parents[1]
        return repo_root / "config" / "security_config.yaml"


@lru_cache
def get_settings() -> Settings:
    return Settings()

