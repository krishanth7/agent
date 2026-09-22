"""Health routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health")
async def read_health() -> HealthResponse:
    """Report that the service is up and identify which build is running.

    Only one health route is exposed. Separate liveness and readiness probes
    would be meaningful once there are downstream dependencies whose
    availability differs from the process's own — a database, a broker
    session, a market-data feed. With none of those connected yet, the two
    probes would return identical information, and a readiness check that
    cannot actually fail is worse than no readiness check: it looks like a
    guarantee while providing none.
    """
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.app_version,
        environment=settings.environment,
    )
