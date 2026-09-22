"""Typed application configuration.

Every knob is read from the environment through pydantic-settings so nothing
is hard-coded and no secret ever needs to live in source.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production"]


class Settings(BaseSettings):
    """Application settings, populated from the environment or `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
        frozen=True,
    )

    app_name: str = "NIFTY Trading Agent API"
    app_version: str = "0.2.0"
    service_name: str = "nifty-trading-agent-api"
    environment: Environment = "development"
    debug: bool = False

    api_v1_prefix: str = "/api/v1"

    #: Explicit browser origins allowed to call the API. Never widened to "*",
    #: because the CORS middleware is configured with credentials enabled.
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    #: Exchange-local timezone for all trading-domain dates.
    timezone: str = "Asia/Kolkata"

    log_level: Annotated[
        str, Field(pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    ] = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string as well as a JSON array.

        `CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000` is far more
        natural to write in a shell than the JSON pydantic-settings expects.
        """
        if isinstance(value, str) and not value.strip().startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def docs_enabled(self) -> bool:
        """Interactive API docs are a development affordance only."""
        return not self.is_production


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton.

    Cached so the environment is read once; tests clear the cache when they
    need to exercise a different configuration.
    """
    return Settings()
