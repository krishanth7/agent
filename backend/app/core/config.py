"""Typed application configuration.

Every knob is read from the environment through pydantic-settings so nothing
is hard-coded and no secret ever needs to live in source.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

Environment = Literal["development", "staging", "production"]

#: Which repository implementation the application runs against.
#:
#: `postgres` is the real one and the default. `mock` exists so the unit suite
#: — which asserts on routing, validation, serialization and the calculation
#: rules — can run without a database, and so the API remains inspectable on a
#: machine where Docker is not available. It is not a fallback: nothing selects
#: it automatically, and a failed database connection surfaces as an error
#: rather than quietly serving invented figures.
RepositoryBackend = Literal["postgres", "mock"]


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

    repository_backend: RepositoryBackend = "postgres"

    # -- PostgreSQL ---------------------------------------------------------
    #
    # Assembled from parts rather than taking a single URL, because a URL in an
    # environment variable is the classic way a password ends up in a shell
    # history, a log line or a crash report. `postgres_password` is a
    # `SecretStr`, so it renders as `**********` anywhere a model is printed.

    postgres_db: str = "trading_agent"
    postgres_user: str = "trading_agent"
    postgres_password: SecretStr = SecretStr("trading_agent_dev_password")
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    #: Connection pool sizing. Deliberately modest: this is a single-user
    #: dashboard backend, and an oversized pool only moves the queue from the
    #: application into PostgreSQL, which has a far lower connection ceiling.
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout: int = 30
    #: Recycle below the typical cloud idle-connection cut-off, so the pool
    #: retires a connection before a proxy silently kills it under us.
    db_pool_recycle: int = 1800
    #: Emit every statement. Useful when debugging a query, far too noisy
    #: otherwise, and it would log bound parameters.
    db_echo: bool = False

    #: Ceiling on the health endpoint's `SELECT 1`.
    #:
    #: Sized from measurement, not taste. The engine is created lazily, so the
    #: first probe in a process pays for the whole connection establishment —
    #: TCP, authentication, and asyncpg's type-codec setup. Measured on the
    #: development stack: ~2,170 ms cold, ~5 ms once pooled. An earlier 2.0 s
    #: budget therefore reported a perfectly healthy database as `timeout` on
    #: the first request, which is the worst kind of health check: one that
    #: fails when nothing is wrong.
    #:
    #: 5.0 s leaves headroom over the measured cold path while staying under a
    #: typical orchestrator probe timeout and well under `db_pool_timeout`, so
    #: a saturated pool still reports as a failing probe rather than blocking
    #: one. Note the cold cost is partly the WSL localhost relay; a native
    #: Linux host connects considerably faster.
    db_health_timeout: float = 5.0

    @property
    def database_url(self) -> URL:
        """Async SQLAlchemy URL for the application.

        Returned as a `URL` object rather than a string so the password stays
        wrapped: `repr(URL)` masks it, whereas an f-string would splice the
        plaintext into anything that logs the value.
        """
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def safe_database_url(self) -> str:
        """Connection target with the credentials stripped, safe to log."""
        return (
            f"postgresql://{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

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
