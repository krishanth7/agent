"""Health routes.

THREE PROBES, THREE QUESTIONS
-----------------------------
Phase 2 exposed a single `/health`, on the grounds that with no downstream
dependencies a readiness check could not actually fail — and a check that
cannot fail is worse than none, because it looks like a guarantee. A database
is now a dependency, so that reasoning inverts and the probes separate:

* ``/health/live``  — is this process running? Never touches the database.
* ``/health/ready`` — can it actually serve requests? 503 when it cannot.
* ``/health``       — the human-readable view: identity plus dependency state.

The split matters operationally. A liveness probe that fails during a database
outage tells the orchestrator to restart a perfectly healthy process, turning a
brief blip into a restart loop that guarantees a longer outage.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.db.health import DatabaseStatus, check_database
from app.dependencies import SettingsDep
from app.schemas.health import DatabaseHealth, HealthResponse, LivenessResponse

router = APIRouter(tags=["health"])


async def _probe(settings: SettingsDep) -> DatabaseStatus:
    """Probe the database, unless this deployment has none.

    Under the mock backend there is no engine and no connection string, so
    probing would either fabricate a failure or attempt a connection the
    operator never configured.
    """
    if settings.repository_backend != "postgres":
        return DatabaseStatus(state="not_configured")
    return await check_database(settings.db_health_timeout)


def _to_schema(probe: DatabaseStatus) -> DatabaseHealth:
    return DatabaseHealth(
        state=probe.state, latency_ms=probe.latency_ms, error=probe.error
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health and dependency state",
    responses={503: {"model": HealthResponse, "description": "A dependency is down."}},
)
async def read_health(settings: SettingsDep, response: Response) -> HealthResponse:
    """Report service identity and whether its dependencies are reachable.

    Returns 503 with a populated body when the database is unreachable. The
    body is deliberately still rendered: an operator needs to know which
    dependency failed, and a bare 503 tells them nothing.
    """
    probe = await _probe(settings)

    if not probe.is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ok" if probe.is_healthy else "degraded",
        service=settings.service_name,
        version=settings.app_version,
        environment=settings.environment,
        database=_to_schema(probe),
    )


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    summary="Process liveness",
)
async def read_liveness(settings: SettingsDep) -> LivenessResponse:
    """Answer whether the process is up, without touching any dependency.

    Always 200 while the process can serve a request at all. That is the whole
    contract — see the module docstring for why it must not consult the
    database.
    """
    return LivenessResponse(
        status="alive",
        service=settings.service_name,
        version=settings.app_version,
    )


@router.get(
    "/health/ready",
    response_model=HealthResponse,
    summary="Readiness to serve traffic",
    responses={
        503: {"model": HealthResponse, "description": "Not ready to serve traffic."}
    },
)
async def read_readiness(settings: SettingsDep, response: Response) -> HealthResponse:
    """Answer whether the service can serve real requests right now.

    Distinct from liveness: this one *is* allowed to fail on a dependency
    outage, because the correct response to an unreachable database is to stop
    routing traffic here — not to restart the process.
    """
    return await read_health(settings, response)
