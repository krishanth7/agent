"""Health endpoint and cross-cutting middleware behaviour."""

from __future__ import annotations

from app.core.middleware import REQUEST_ID_HEADER
from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient, api: str) -> None:
    """Under the mock backend there is no database to be unready about."""
    response = await client.get(f"{api}/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "nifty-trading-agent-api",
        "version": "0.2.0",
        "environment": "development",
        "database": {"state": "not_configured", "latency_ms": None, "error": None},
    }


async def test_liveness_never_consults_the_database(
    client: AsyncClient, api: str
) -> None:
    """Liveness must answer from the process alone.

    Asserted structurally — the payload has no `database` key at all — so the
    contract cannot regress into "alive means the database is up", which is
    what turns a brief outage into a restart loop.
    """
    response = await client.get(f"{api}/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "alive",
        "service": "nifty-trading-agent-api",
        "version": "0.2.0",
    }


async def test_readiness_reports_dependency_state(
    client: AsyncClient, api: str
) -> None:
    response = await client.get(f"{api}/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"]["state"] == "not_configured"


async def test_health_never_leaks_connection_details(
    client: AsyncClient, api: str
) -> None:
    """The least protected route in the system must not describe the topology.

    A guard against a future change that helpfully includes the driver's error
    text — which routinely carries host, port, database name and username.
    """
    body = (await client.get(f"{api}/health")).text.lower()

    for secret in ("password", "postgresql://", "asyncpg", "5432", "localhost"):
        assert secret not in body, secret


async def test_response_carries_a_request_id(client: AsyncClient, api: str) -> None:
    response = await client.get(f"{api}/health")
    assert response.headers[REQUEST_ID_HEADER]


async def test_inbound_request_id_is_echoed(client: AsyncClient, api: str) -> None:
    """Lets a trace span the frontend and the API."""
    response = await client.get(
        f"{api}/health", headers={REQUEST_ID_HEADER: "trace-abc-123"}
    )
    assert response.headers[REQUEST_ID_HEADER] == "trace-abc-123"


async def test_oversized_request_id_is_truncated(client: AsyncClient, api: str) -> None:
    """A client must not be able to push unbounded text into the logs."""
    response = await client.get(f"{api}/health", headers={REQUEST_ID_HEADER: "x" * 500})
    assert len(response.headers[REQUEST_ID_HEADER]) == 128


async def test_unknown_route_uses_the_error_envelope(
    client: AsyncClient, api: str
) -> None:
    response = await client.get(f"{api}/does-not-exist")

    assert response.status_code == 404
    assert "error" in response.json()
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_openapi_document_is_served(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["version"] == "0.2.0"
    assert "/api/v1/health" in schema["paths"]


async def test_no_order_endpoints_exist(client: AsyncClient) -> None:
    """Phase 2 must expose no order path of any kind.

    A structural guard: if someone later adds a trading route without the
    surrounding risk machinery, this fails loudly.
    """
    schema = (await client.get("/openapi.json")).json()
    forbidden = (
        "buy",
        "sell",
        "trade",
        "execute",
        "order",
        "exit",
        "predict",
        "signal",
    )

    for path, operations in schema["paths"].items():
        assert not any(token in path.lower() for token in forbidden), path
        # Only read methods and the single target write are permitted.
        assert set(operations) <= {"get", "put"}, path
