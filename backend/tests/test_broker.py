"""The `/broker` routes.

NO SOCKET, BUT THE REAL REQUEST PATH
------------------------------------
These drive the routes through `ASGITransport` and the broker through
`httpx.MockTransport`, so both fakes sit at the outermost layer on each side.
Everything between them is the production code: FastAPI's dependency resolution,
the response-model validation, the service, the authenticator, the mapper, and
the error handler that turns a `BrokerError` into an envelope. Only the two wires
are substituted.

This matters most for the response models. `ApiModel` is `extra="forbid"` and
`order_placement_available` is `Literal[False]`, and neither guarantee is worth
anything unless something actually validates a response through them.

WHAT THE SECURITY TESTS HERE CAN AND CANNOT ESTABLISH
-----------------------------------------------------
`TestNoSecretsInResponses` asserts that the raw response text contains none of
the fake credentials the test itself configured. That is a genuine end-to-end
check — the tokens exist in the process, the adapter is holding them, and the
assertion is that none of them reached the body.

What it cannot establish is that no *future* field leaks something these tests
never set. The structural defences for that are elsewhere and are not tests: the
schema forbids undeclared fields, and the tokens are `SecretStr`, so even a
mistaken interpolation renders as asterisks.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import httpx
import pytest
from app.brokers.angel_one.adapter import AngelOneAdapter
from app.brokers.angel_one.constants import ROUTE_LOGIN, ROUTE_PROFILE
from app.brokers.models import BrokerSession
from app.core.config import Settings
from app.core.constants import IST
from app.main import create_app
from app.schemas.broker import BrokerStatusResponse
from app.services.broker_service import BrokerService, mask_client_code
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr, ValidationError

from tests.brokers.conftest import (
    FEED_TOKEN,
    JWT_TOKEN,
    LOGIN_DATA,
    REFRESH_TOKEN,
    TOTP_SECRET,
    RecordingRouter,
    broker_settings,
    envelope,
)

pytestmark = pytest.mark.asyncio

PROFILE_DATA = {
    "clientcode": "T0000001",
    "name": "Test Account",
    "exchanges": ["NSE", "NFO"],
}


def app_client(
    settings: Settings, router: RecordingRouter | None = None
) -> AsyncClient:
    """An HTTP client for an app whose broker talks to `router`.

    The service is planted on app state rather than injected with a dependency
    override, because app state is where the real provider caches it. Overriding
    the dependency would test a path production never takes; this way the test
    proves the caching contract too — a second request finds this same service,
    session and all.

    `router=None` leaves the app with no pre-built service, so the real provider
    constructs one and the adapter would attempt a real login. Every test that
    does this is a test where credentials are absent, so no adapter is ever
    built — which is the behaviour being asserted.
    """
    app = create_app(settings)
    if router is not None:
        app.state.broker_service = BrokerService(
            settings,
            adapter_factory=lambda: AngelOneAdapter(
                settings, transport=httpx.MockTransport(router)
            ),
        )
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def connected_router() -> RecordingRouter:
    """A router that answers login and profile successfully."""
    routes = RecordingRouter()
    routes.json_response(ROUTE_LOGIN, envelope(LOGIN_DATA))
    routes.json_response(ROUTE_PROFILE, envelope(PROFILE_DATA))
    return routes


async def get(client: AsyncClient, path: str) -> httpx.Response:
    return await client.get(f"/api/v1/broker{path}")


class TestStatusWithoutCredentials:
    """The default deployment: nothing configured, and the endpoint still works.

    This is the case most likely to be broken by a careless refactor, because
    it is the one where every optional setting is `None` and the adapter cannot
    be constructed at all.
    """

    async def test_status_is_served_when_nothing_is_configured(self) -> None:
        """200, not an error. A fresh install is not a failed request."""
        settings = Settings(
            environment="development", log_level="WARNING", repository_backend="mock"
        )
        async with app_client(settings) as client:
            response = await get(client, "/status")

        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is False
        assert body["configured"] is False
        assert body["connected"] is False

    async def test_an_unconfigured_status_reports_no_client_code(self) -> None:
        """`None`, not an empty string and not a masked placeholder.

        An empty string would render as a blank field in the dashboard, which
        reads as "connected to an account with no name" rather than "no account".
        """
        settings = Settings(
            environment="development", log_level="WARNING", repository_backend="mock"
        )
        async with app_client(settings) as client:
            body = (await get(client, "/status")).json()

        assert body["client_code"] is None
        assert body["session_expires_at"] is None

    async def test_status_makes_no_broker_call_when_unconfigured(self) -> None:
        """The proof is that the test passes at all.

        No router is supplied, so the real provider builds the service and any
        attempt to construct an adapter would raise `BrokerConfigurationError`
        and surface as a 409. A 200 means nothing tried.
        """
        settings = Settings(
            environment="development", log_level="WARNING", repository_backend="mock"
        )
        async with app_client(settings) as client:
            assert (await get(client, "/status")).status_code == 200

    async def test_a_connection_test_without_credentials_is_a_409(self) -> None:
        """Not a 5xx. Nothing is broken; the operator has not finished setup,
        and no amount of retrying will change that."""
        settings = Settings(
            environment="development", log_level="WARNING", repository_backend="mock"
        )
        async with app_client(settings) as client:
            response = await get(client, "/connection-test")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "BROKER_NOT_CONFIGURED"


class TestStatusWhenConfigured:
    async def test_configured_but_not_yet_connected(self) -> None:
        """The third distinct state, and the reason there are three booleans.

        Credentials are present and the switch is on, but nothing has asked for
        broker data yet, so there is no session. Reporting this as `connected`
        would claim a working credential that has never been tested.
        """
        settings = broker_settings()
        async with app_client(settings, connected_router()) as client:
            body = (await get(client, "/status")).json()

        assert body["enabled"] is True
        assert body["configured"] is True
        assert body["connected"] is False
        assert body["session_expires_at"] is None

    async def test_status_reports_connected_after_a_connection_test(self) -> None:
        """The session outlives the request that created it.

        Two requests against one app. The second sees `connected: true` only
        because the service — and therefore the session — is cached on app
        state, which is the whole reason it is cached there.
        """
        settings = broker_settings()
        async with app_client(settings, connected_router()) as client:
            assert (await get(client, "/connection-test")).status_code == 200
            body = (await get(client, "/status")).json()

        assert body["connected"] is True
        assert body["session_expires_at"] is not None

    async def test_enabled_can_be_false_while_credentials_are_present(self) -> None:
        """The master switch is independent of completeness.

        `configured` is false here despite every credential being set, because
        `angel_one_configured` includes the switch. Both are reported so the
        dashboard can say "you have set this up but not turned it on" rather
        than sending an operator to re-check credentials that are fine.
        """
        settings = broker_settings(angel_one_enabled=False)
        async with app_client(settings, connected_router()) as client:
            body = (await get(client, "/status")).json()

        assert body["enabled"] is False
        assert body["configured"] is False
        assert body["client_code"] is not None

    async def test_a_blank_credential_reads_as_absent_not_as_empty(self) -> None:
        """`ANGEL_ONE_PIN=` in a copied template must not report "configured".

        The failure guarded against here is a misdiagnosis, not a crash. An
        empty string passes `is not None`, so without the settings validator
        this app would call itself configured, send a blank PIN to Angel One,
        and report `BROKER_AUTHENTICATION_FAILED` — telling an operator their
        credentials were *rejected* when in fact one line of their `.env` was
        never filled in. Those two states have different remedies, and the
        whole point of reporting `enabled`, `configured` and `connected`
        separately is to keep them apart.

        A trailing-whitespace value is included because a secret pasted with a
        newline is blank in every sense that matters.
        """
        settings = broker_settings(angel_one_pin="", angel_one_totp_secret="   ")

        assert settings.angel_one_pin is None
        assert settings.angel_one_totp_secret is None
        assert settings.angel_one_configured is False

        async with app_client(settings) as client:
            body = (await get(client, "/status")).json()

        assert body["enabled"] is True
        assert body["configured"] is False
        assert body["connected"] is False


class TestConnectionTest:
    async def test_a_successful_test_reports_the_account_the_broker_returned(
        self,
    ) -> None:
        settings = broker_settings()
        async with app_client(settings, connected_router()) as client:
            response = await get(client, "/connection-test")

        assert response.status_code == 200
        body = response.json()
        assert body["connected"] is True
        assert body["client_name"] == "Test Account"
        assert body["exchanges"] == ["NSE", "NFO"]
        assert body["session_expires_at"] is not None
        assert body["checked_at"] is not None

    async def test_the_test_authenticates_then_reads_the_profile(self) -> None:
        """Both steps, in that order, observed on the wire.

        Either alone proves less than it looks like. A login says the
        credentials are good but not that the account can be read.
        """
        settings = broker_settings()
        router = connected_router()
        async with app_client(settings, router) as client:
            await get(client, "/connection-test")

        assert router.paths() == [ROUTE_LOGIN, ROUTE_PROFILE]

    async def test_a_second_test_does_not_log_in_again(self) -> None:
        """Angel One permits one login per second, and a TOTP code cannot be
        reused inside its window. A status badge that a user clicks twice must
        not be a way to lock the account."""
        settings = broker_settings()
        router = connected_router()
        async with app_client(settings, router) as client:
            await get(client, "/connection-test")
            await get(client, "/connection-test")

        assert router.paths().count(ROUTE_LOGIN) == 1
        assert router.paths().count(ROUTE_PROFILE) == 2

    async def test_rejected_credentials_are_a_502_not_a_200(self) -> None:
        """The distinction the whole design of the response model rests on.

        A 200 body saying `connected: false` would be invisible to every client
        that checks a status code, which is most of them.
        """
        settings = broker_settings()
        routes = RecordingRouter()
        routes.json_response(
            ROUTE_LOGIN,
            envelope(None, status=False, errorcode="AB1007"),
        )
        async with app_client(settings, routes) as client:
            response = await get(client, "/connection-test")

        assert response.status_code == 502
        assert response.json()["error"]["code"] == "BROKER_AUTHENTICATION_FAILED"

    async def test_the_client_code_comes_from_the_broker_not_the_config(self) -> None:
        """A login against the wrong account must be visible.

        The profile here reports a different code than the settings configure.
        Echoing the configured value back would make the two cases identical,
        which defeats the point of a connection test.
        """
        settings = broker_settings()
        routes = RecordingRouter()
        routes.json_response(ROUTE_LOGIN, envelope(LOGIN_DATA))
        routes.json_response(ROUTE_PROFILE, envelope({"clientcode": "T9999999"}))
        async with app_client(settings, routes) as client:
            body = (await get(client, "/connection-test")).json()

        assert body["client_code"] == mask_client_code("T9999999")
        assert body["client_code"] != mask_client_code("T0000001")


class ExpiredSessionAdapter(AngelOneAdapter):
    """A real adapter whose session is always already over.

    Subclassing to override one public property, rather than writing a fake
    adapter: everything else — construction, credential checks, the HTTP client
    — is the production code. Only the clock's verdict is forced, which is the
    one thing a test cannot otherwise arrange without waiting for midnight IST.
    """

    @property
    def session(self) -> BrokerSession | None:
        return BrokerSession(
            access_token=SecretStr(JWT_TOKEN),
            refresh_token=SecretStr(REFRESH_TOKEN),
            feed_token=SecretStr(FEED_TOKEN),
            issued_at=dt.datetime(2020, 1, 1, tzinfo=IST),
            expires_at=dt.datetime(2020, 1, 2, tzinfo=IST),
            client_code="T0000001",
        )


class TestExpiredSession:
    async def test_a_lapsed_session_is_reported_as_not_connected(self) -> None:
        """An expired token is not a connection.

        The adapter would silently re-authenticate on the next data call, so
        nothing would visibly break — which is precisely the danger. Reporting
        `connected: true` here would have the status endpoint assert a live
        connection on the strength of a credential the broker has already
        stopped accepting.
        """
        settings = broker_settings()
        router = connected_router()
        service = BrokerService(
            settings,
            adapter_factory=lambda: ExpiredSessionAdapter(
                settings, transport=httpx.MockTransport(router)
            ),
        )
        # Force the adapter into existence the way a real request would, then
        # ask for status. `test_connection` is what a user clicks first.
        await service.test_connection()
        status = await service.get_status()

        assert status.connected is False
        assert status.session_expires_at is None

    async def test_a_lapsed_session_does_not_leak_its_expiry(self) -> None:
        """`session_expires_at` is `None`, not a timestamp in the past.

        A past timestamp would render in the dashboard as an expiry, inviting a
        reader to conclude the session is live until then.
        """
        settings = broker_settings()
        service = BrokerService(
            settings,
            adapter_factory=lambda: ExpiredSessionAdapter(
                settings, transport=httpx.MockTransport(connected_router())
            ),
        )
        await service.test_connection()
        assert (await service.get_status()).session_expires_at is None


class TestClientCodeMasking:
    # The first three are `async` only to satisfy the module-level asyncio
    # mark; they call a pure function and touch neither app nor network.

    async def test_only_the_last_two_characters_survive(self) -> None:
        assert mask_client_code("T0000001") == "******01"

    async def test_a_short_code_is_masked_completely(self) -> None:
        """Rather than returned as-is because masking would not hide much.

        A redaction helper with a length threshold below which it returns the
        input unchanged is a redaction helper that leaks.
        """
        assert mask_client_code("AB") == "**"
        assert mask_client_code("A") == "*"

    async def test_masking_preserves_length(self) -> None:
        """So the field still looks like an account code in the UI, and so two
        different accounts cannot be made to render identically."""
        assert len(mask_client_code("T0000001")) == len("T0000001")

    async def test_the_configured_code_is_never_sent_in_full(self) -> None:
        settings = broker_settings()
        async with app_client(settings, connected_router()) as client:
            status_text = (await get(client, "/status")).text
            test_text = (await get(client, "/connection-test")).text

        assert "T0000001" not in status_text
        assert "T0000001" not in test_text


class TestNoSecretsInResponses:
    """No token, PIN, TOTP seed or API key in any broker response body."""

    @staticmethod
    def _secrets() -> dict[str, str]:
        """Named so a failure says *which* secret leaked."""
        return {
            "jwt": JWT_TOKEN,
            "refresh": REFRESH_TOKEN,
            "feed": FEED_TOKEN,
            "totp_secret": TOTP_SECRET,
            "api_key": "fake-api-key",
            "pin": "0000",
        }

    async def test_the_status_body_contains_no_secret(self) -> None:
        settings = broker_settings()
        async with app_client(settings, connected_router()) as client:
            await get(client, "/connection-test")  # so tokens are held in memory
            text = (await get(client, "/status")).text

        for name, secret in self._secrets().items():
            assert secret not in text, f"{name} leaked into the status body"

    async def test_the_connection_test_body_contains_no_secret(self) -> None:
        settings = broker_settings()
        async with app_client(settings, connected_router()) as client:
            text = (await get(client, "/connection-test")).text

        for name, secret in self._secrets().items():
            assert secret not in text, f"{name} leaked into the connection-test body"

    async def test_no_response_field_is_named_like_a_credential(self) -> None:
        """Belt and braces against a field added later.

        Checks the key names rather than the values, so it fires even if a
        future token field happened to be empty at the time the test ran.
        """
        settings = broker_settings()
        async with app_client(settings, connected_router()) as client:
            keys = set((await get(client, "/connection-test")).json())
            keys |= set((await get(client, "/status")).json())

        forbidden = {"token", "secret", "password", "pin", "key", "jwt"}
        for key in keys:
            assert not any(word in key.lower() for word in forbidden), key


class TestReadOnly:
    """The routes are a window, not a lever."""

    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    @pytest.mark.parametrize("path", ["/status", "/connection-test"])
    async def test_no_write_method_is_accepted(self, method: str, path: str) -> None:
        settings = broker_settings()
        async with app_client(settings, connected_router()) as client:
            response = await client.request(method, f"/api/v1/broker{path}")

        assert response.status_code == 405

    @pytest.mark.parametrize(
        "path",
        [
            "/buy",
            "/sell",
            "/order",
            "/orders",
            "/trade",
            "/execute",
            "/exit",
            "/exit-all",
            "/square-off",
            "/place-order",
            "/cancel-order",
            "/modify-order",
        ],
    )
    async def test_no_order_route_exists(self, path: str) -> None:
        """404 on every verb, not 405 — the path is not routed at all.

        A 405 would mean the path exists for some other method, which is the
        situation this asserts against: a route that exists and rejects the
        method is one decorator away from a route that accepts it.
        """
        settings = broker_settings()
        async with app_client(settings, connected_router()) as client:
            for method in ("get", "post", "put", "delete"):
                response = await client.request(method, f"/api/v1/broker{path}")
                assert response.status_code == 404, f"{method.upper()} {path}"

    async def test_the_openapi_schema_declares_no_broker_write_operation(self) -> None:
        """Read from the schema, so this covers routes no test thought to name.

        The parametrized test above can only check paths someone predicted. This
        one fails for any write operation added under `/broker`, whatever it is
        called.
        """
        settings = broker_settings()
        async with app_client(settings, connected_router()) as client:
            schema = (await client.get("/openapi.json")).json()

        broker_paths = {
            path: operations
            for path, operations in schema["paths"].items()
            if "/broker" in path
        }
        assert broker_paths, "the broker routes are missing from the schema"
        for path, operations in broker_paths.items():
            methods = set(operations) - {"parameters"}
            assert methods == {"get"}, f"{path} exposes {methods}"

    async def test_no_order_operation_exists_anywhere_in_the_api(self) -> None:
        """Not just under `/broker`. The prohibition is on the whole service.

        Scans every path in the schema for an order verb rather than probing
        paths by name, so it fails for an order route added under any prefix by
        any future phase that has not first built a risk engine.
        """
        settings = broker_settings()
        async with app_client(settings, connected_router()) as client:
            schema = (await client.get("/openapi.json")).json()

        forbidden = (
            "buy",
            "sell",
            "order",
            "trade",
            "execute",
            "exit",
            "square",
            "position",
        )
        for path in schema["paths"]:
            lowered = path.lower()
            assert not any(word in lowered for word in forbidden), path

    async def test_order_placement_is_reported_as_unavailable(self) -> None:
        """Stated in the payload, not merely implied by the absence of a route.

        An operator must be able to confirm the fact by reading a field.
        """
        settings = broker_settings()
        async with app_client(settings, connected_router()) as client:
            body = (await get(client, "/status")).json()

        assert body["order_placement_available"] is False
        assert body["live_trading_enabled"] is False
        assert body["paper_trading_enabled"] is False


class TestSchemaGuarantees:
    async def test_an_undeclared_field_cannot_be_returned(self) -> None:
        """`extra="forbid"` on the response model, asserted rather than trusted.

        This is the structural defence that makes the secret-scanning tests
        above more than a check on the values they happened to know about: a
        service that tried to attach a token to a response would fail here.
        """
        with pytest.raises(ValidationError):
            BrokerStatusResponse(
                broker="angel_one",
                enabled=False,
                configured=False,
                connected=False,
                live_trading_enabled=False,
                paper_trading_enabled=False,
                access_token="leaked",  # type: ignore[call-arg]
            )

    async def test_order_placement_available_cannot_be_set_true(self) -> None:
        """`Literal[False]`, so the schema cannot express the claim at all.

        A change that tried to advertise order placement would fail validation
        rather than quietly succeed.
        """
        fields: dict[str, Any] = {
            "broker": "angel_one",
            "enabled": False,
            "configured": False,
            "connected": False,
            "live_trading_enabled": False,
            "paper_trading_enabled": False,
            "order_placement_available": True,
        }
        with pytest.raises(ValidationError):
            BrokerStatusResponse(**fields)
