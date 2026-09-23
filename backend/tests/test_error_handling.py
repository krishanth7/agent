"""How failures leave the application.

These tests exist because of a real defect. Stopping the database produced an
unhandled `ConnectionRefusedError`, which surfaced as a 500 with a traceback —
the wrong status (500 says "broken, retrying is pointless"; a stopped database
is retryable) and an information leak. Fixing it once is not enough: the
failure mode is invisible in normal development, so without a test it would
come back the next time someone touched the handler list.

The app used here is the real one, with its real middleware stack. The routes
are added afterwards purely as a way to inject a specific exception type at the
point a route would raise it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from app.core.config import Settings
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

#: A driver message of the kind that must never reach a client. Modelled on
#: what asyncpg actually produces: topology and a valid username in one line.
_LEAKY_DRIVER_TEXT = (
    'connection to server at "10.0.3.14", port 5432 failed: '
    'FATAL: password authentication failed for user "trading_agent"'
)


@pytest_asyncio.fixture
async def failing_client(settings: Settings) -> AsyncIterator[AsyncClient]:
    """A client for an app whose routes fail in specific, chosen ways."""
    app = create_app(settings)

    @app.get("/boom/sqlalchemy")
    async def _boom_sqlalchemy() -> None:
        raise OperationalError(
            "SELECT target_amount FROM monthly_targets",
            {"year": 2026},
            Exception(_LEAKY_DRIVER_TEXT),
        )

    @app.get("/boom/connection")
    async def _boom_connection() -> None:
        # What a refused TCP connection actually looks like: a bare OSError
        # raised by the event loop's socket layer, before asyncpg has a DBAPI
        # error to wrap and before SQLAlchemy can translate it.
        raise ConnectionRefusedError(
            1225, "The remote computer refused the network connection"
        )

    @app.get("/boom/unexpected")
    async def _boom_unexpected() -> None:
        raise RuntimeError("an internal invariant naming /srv/app/secrets.yml")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.parametrize("path", ["/boom/sqlalchemy", "/boom/connection"])
async def test_database_failure_is_a_503(
    failing_client: AsyncClient, path: str
) -> None:
    """Both database failure shapes must produce the same retryable answer.

    503, not 500. The distinction is what a load balancer, a retry policy and
    an orchestrator all key on: 503 means "this request would have worked, try
    again", which is true and actionable.
    """
    response = await failing_client.get(path)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"


@pytest.mark.parametrize("path", ["/boom/sqlalchemy", "/boom/connection"])
async def test_database_failure_leaks_nothing(
    failing_client: AsyncClient, path: str
) -> None:
    """The message is fixed, so no driver text can ride out on it."""
    body = (await failing_client.get(path)).text.lower()

    for secret in (
        "password",
        "trading_agent",
        "10.0.3.14",
        "5432",
        "select",
        "traceback",
        "operationalerror",
    ):
        assert secret not in body, secret


async def test_database_failure_states_that_nothing_changed(
    failing_client: AsyncClient,
) -> None:
    """A user deciding whether to retry needs to know it is safe to.

    The session rolls back on any exception, so a failed write changed
    nothing — and saying so is the difference between a confident retry and a
    user wondering whether they just double-submitted a target change.
    """
    message = (await failing_client.get("/boom/connection")).json()["error"]["message"]

    assert "no data has been changed" in message.lower()


async def test_unexpected_failure_is_a_generic_500(
    failing_client: AsyncClient,
) -> None:
    """Anything unanticipated still leaves through the same envelope."""
    response = await failing_client.get("/boom/unexpected")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}
    }
    # The exception text named a filesystem path. It stayed in the log.
    assert "secrets.yml" not in response.text


async def test_validation_failure_does_not_echo_the_submitted_value(
    client: AsyncClient, api: str
) -> None:
    """Pydantic's raw error list carries `input`; the envelope must not.

    Echoing the submitted value back into the response body is how a
    reflection vector gets built by accident, and for this API the submitted
    value is a monetary amount.
    """
    response = await client.put(
        f"{api}/targets/monthly", json={"monthly_target": "<script>alert(1)</script>"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "<script>" not in response.text
