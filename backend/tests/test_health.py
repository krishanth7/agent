"""Health endpoint and cross-cutting middleware behaviour."""

from __future__ import annotations

from app.core.middleware import REQUEST_ID_HEADER
from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient, api: str) -> None:
    response = await client.get(f"{api}/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "nifty-trading-agent-api",
        "version": "0.2.0",
        "environment": "development",
    }


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
