"""Health API schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel


class DatabaseHealth(ApiModel):
    """Reachability of the PostgreSQL dependency.

    Carries no host, port, username, database name or driver text. See
    `app.db.health` for why the failure category is deliberately coarse.
    """

    state: Literal["up", "down", "not_configured"] = Field(
        description=(
            "`not_configured` means the service is running against the "
            "in-memory mock backend and has no database to reach."
        )
    )
    latency_ms: float | None = Field(
        default=None, description="Probe round-trip time in milliseconds."
    )
    error: str | None = Field(
        default=None,
        description=(
            "Failure category — `timeout` or `unavailable`. Never a driver "
            "message, which would leak connection details."
        ),
    )


class LivenessResponse(ApiModel):
    """Whether the process itself is running.

    Deliberately answers without touching the database. A liveness probe that
    fails on a dependency outage tells the orchestrator to restart a process
    that is working perfectly, which turns a recoverable database blip into a
    restart loop.
    """

    status: Literal["alive"]
    service: str
    version: str


class HealthResponse(ApiModel):
    """Service identity plus the state of its dependencies.

    Free of build paths, hostnames and configuration: a health endpoint is
    usually the least protected route in a system, so it should reveal nothing
    an attacker could use to fingerprint the deployment beyond the version
    already published in the OpenAPI document.

    `status` is `degraded` — and the HTTP status 503 — whenever a dependency is
    down. The body is still returned, because an operator needs to know *which*
    dependency failed, and an empty 503 tells them nothing.
    """

    status: Literal["ok", "degraded"]
    service: str
    version: str
    environment: str
    database: DatabaseHealth
