"""Health endpoints against a real database — reachable and not.

The unreachable case is exercised by pointing the engine at a port nothing
listens on, rather than by stopping the container. Same failure at the socket
layer (`ConnectionRefusedError` from the event loop, before asyncpg or
SQLAlchemy see anything), no shared state torn down underneath other tests,
and it runs anywhere — including CI, where the ability to stop the database is
not something a test should assume it has.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest_asyncio
from app.core.config import Settings, get_settings
from app.db.session import dispose_engine
from app.main import create_app
from httpx import ASGITransport, AsyncClient

_LEAKABLE = ("password", "asyncpg", "postgresql://", "5432", "localhost", "traceback")


@pytest_asyncio.fixture
async def unreachable_client(database_settings: Settings) -> AsyncIterator[AsyncClient]:
    """An app whose database is configured to a port nothing listens on."""
    original = os.environ.get("POSTGRES_PORT")
    # Disposed first: the pooled connections belong to the *reachable*
    # database, and handing one of them out would make this fixture a no-op.
    await dispose_engine()
    os.environ["POSTGRES_PORT"] = "1"
    get_settings.cache_clear()

    settings = get_settings().model_copy(update={"repository_backend": "postgres"})
    transport = ASGITransport(app=create_app(settings))
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        # Order matters: drop the engine built against the bad port, restore
        # the environment, and only then clear the cache — so the next caller
        # of `get_settings` repopulates it from the restored environment.
        await dispose_engine()
        if original is None:
            os.environ.pop("POSTGRES_PORT", None)
        else:
            os.environ["POSTGRES_PORT"] = original
        get_settings.cache_clear()


async def test_health_reports_the_database_as_up(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"]["state"] == "up"
    assert payload["database"]["error"] is None
    # A latency is reported because the probe actually round-tripped.
    assert payload["database"]["latency_ms"] is not None


async def test_readiness_reports_the_database_as_up(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["database"]["state"] == "up"


async def test_health_is_503_when_the_database_is_unreachable(
    unreachable_client: AsyncClient,
) -> None:
    """§58: an outage must look like an outage.

    A 200 with `state: down` would be worse than useless — every orchestrator
    and load balancer keys on the status code, and a probe that returns 200
    while the dependency is dead keeps traffic flowing to an instance that
    cannot serve it.
    """
    response = await unreachable_client.get("/api/v1/health")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["database"]["state"] == "down"
    assert payload["database"]["error"] == "unavailable"


async def test_liveness_stays_ok_when_the_database_is_unreachable(
    unreachable_client: AsyncClient,
) -> None:
    """Liveness answers from the process alone — deliberately.

    If liveness consulted the database, an orchestrator would kill and restart
    every instance during a database outage. Restarting the application cannot
    fix a database that is down; it only removes the capacity that would have
    recovered on its own, turning a brief dependency blip into an outage of
    the service itself.
    """
    response = await unreachable_client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "alive"
    assert "database" not in response.json()


async def test_database_endpoints_are_503_when_the_database_is_unreachable(
    unreachable_client: AsyncClient,
) -> None:
    """No silent fallback to mock figures.

    A dashboard showing an invented ₹4,690 because the database was
    unreachable is worse than one showing an error: the user would act on a
    number that describes nothing and have no way to tell.
    """
    for path in ("/api/v1/targets/monthly", "/api/v1/performance/today"):
        response = await unreachable_client.get(path)

        assert response.status_code == 503, path
        assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE", path


async def test_account_still_answers_when_the_database_is_unreachable(
    unreachable_client: AsyncClient,
) -> None:
    """§42: the account figures never came from the database in the first place.

    Its continuing to answer during an outage is not a fallback — it is the
    honest consequence of there being no broker and no account table.
    """
    response = await unreachable_client.get("/api/v1/account/summary")

    assert response.status_code == 200
    assert response.json()["source"] == "mock"


async def test_failures_describe_nothing_about_the_deployment(
    unreachable_client: AsyncClient,
) -> None:
    """The least protected route must not hand over the topology.

    `connection to server at "10.0.3.14", port 5432 failed: FATAL: password
    authentication failed for user "trading_agent"` is a real asyncpg message.
    It contains a host, a port and a valid username.
    """
    for path in ("/api/v1/health", "/api/v1/targets/monthly"):
        body = (await unreachable_client.get(path)).text.lower()

        for secret in _LEAKABLE:
            assert secret not in body, (path, secret)
