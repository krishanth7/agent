"""The adapter, driven through a mocked transport.

Every test here runs the real client, the real authenticator and the real
mapper. Only the socket is replaced. See `conftest.py` for why that boundary
was chosen.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import httpx
import pytest
from app.brokers.angel_one.adapter import AngelOneAdapter
from app.brokers.angel_one.constants import (
    ROUTE_CANDLE_DATA,
    ROUTE_LOGIN,
    ROUTE_LOGOUT,
    ROUTE_OPTION_GREEK,
    ROUTE_PROFILE,
    ROUTE_RMS_LIMIT,
)
from app.brokers.base import BrokerAdapter
from app.brokers.exceptions import (
    BrokerAuthenticationError,
    BrokerConfigurationError,
    BrokerDataError,
    BrokerError,
    BrokerNetworkError,
    BrokerRateLimitError,
    BrokerUnavailableError,
)
from app.brokers.models import BrokerInstrument
from app.core.constants import IST
from app.domain.enums import InstrumentType, Timeframe
from pydantic import SecretStr

from tests.brokers.conftest import (
    JWT_TOKEN,
    LOGIN_DATA,
    RecordingRouter,
    broker_settings,
    envelope,
)
from tests.brokers.test_mapper import RMS_PAYLOAD

NIFTY = BrokerInstrument(
    token="99926000",
    symbol="NIFTY",
    exchange_segment="NSE",
    instrument_type=InstrumentType.INDEX,
)


def make_adapter(router: RecordingRouter) -> AngelOneAdapter:
    return AngelOneAdapter(broker_settings(), transport=httpx.MockTransport(router))


class TestConfiguration:
    def test_incomplete_credentials_fail_at_construction(self) -> None:
        """Not on first use. A half-built adapter pushes the error to a point
        where the cause is much harder to see."""
        settings = broker_settings(angel_one_totp_secret=None)
        with pytest.raises(BrokerConfigurationError):
            AngelOneAdapter(settings)

    def test_disabled_integration_fails_even_with_full_credentials(self) -> None:
        """The master switch is a switch, not a hint.

        A fully populated `.env` with `ANGEL_ONE_ENABLED=false` must not make
        an outbound call to a broker.
        """
        with pytest.raises(BrokerConfigurationError):
            AngelOneAdapter(broker_settings(angel_one_enabled=False))

    def test_configuration_error_is_409_not_5xx(self) -> None:
        """Nothing is broken. The operator has not finished setting it up, and
        no amount of retrying changes that."""
        assert BrokerConfigurationError().status_code == 409


class TestProtocolConformance:
    def test_the_adapter_satisfies_the_protocol(self) -> None:
        """Structural conformance, checked at runtime as well as by mypy.

        If a method is renamed on one side only, this fails — which is the
        whole value of declaring the contract separately from the class.
        """
        adapter = make_adapter(RecordingRouter())
        assert isinstance(adapter, BrokerAdapter)

    def test_no_order_placement_surface_exists(self) -> None:
        """The read-only guarantee, asserted rather than documented.

        This is the test that fails if someone adds order placement. It is
        deliberately written against names rather than behaviour, because the
        guarantee being protected is the *absence* of a code path.
        """
        forbidden = (
            "place_order",
            "modify_order",
            "cancel_order",
            "square_off",
            "exit_position",
            "buy",
            "sell",
        )
        for name in forbidden:
            assert not hasattr(AngelOneAdapter, name), (
                f"AngelOneAdapter must not expose '{name}'"
            )
            assert not hasattr(BrokerAdapter, name), (
                f"BrokerAdapter must not declare '{name}'"
            )


class TestAuthentication:
    async def test_login_sends_a_six_digit_totp_and_never_the_seed(
        self, router: RecordingRouter
    ) -> None:
        """The seed must not leave the auth module.

        Asserting on the outgoing body is the only way to prove it: a passing
        login tells you nothing about what was in the payload.
        """
        adapter = make_adapter(router)
        await adapter.authenticate()

        body = router.bodies_for(ROUTE_LOGIN)[0]
        assert body["totp"].isdigit()
        assert len(body["totp"]) == 6
        assert "JBSWY3DPEHPK3PXP" not in str(body)

    async def test_session_expiry_is_the_next_ist_midnight(
        self, router: RecordingRouter
    ) -> None:
        """Computed from policy, because the response carries no expiry."""
        adapter = make_adapter(router)
        session = await adapter.authenticate()
        assert session.expires_at.hour == 0
        assert session.expires_at.minute == 0
        assert session.expires_at > session.issued_at

    async def test_tokens_are_wrapped_so_they_cannot_be_printed(
        self, router: RecordingRouter
    ) -> None:
        """A session object ends up in log lines and tracebacks. The worst case
        must be `**********`, not a live credential."""
        adapter = make_adapter(router)
        session = await adapter.authenticate()
        assert JWT_TOKEN not in repr(session)
        assert JWT_TOKEN not in str(session)
        assert session.access_token.get_secret_value() == JWT_TOKEN

    async def test_a_cached_session_does_not_log_in_again(
        self, router: RecordingRouter
    ) -> None:
        """Login is limited to one call per second. An adapter that logs in on
        every request locks itself out."""
        router.json_response(ROUTE_PROFILE, envelope({"clientcode": "T0000001"}))
        adapter = make_adapter(router)
        await adapter.get_profile()
        await adapter.get_profile()
        assert router.paths().count(ROUTE_LOGIN) == 1

    async def test_authenticated_routes_carry_the_bearer_token(
        self, router: RecordingRouter
    ) -> None:
        router.json_response(ROUTE_PROFILE, envelope({"clientcode": "T0000001"}))
        adapter = make_adapter(router)
        await adapter.get_profile()

        profile_request = next(
            r for r in router.requests if r.url.path == ROUTE_PROFILE
        )
        assert profile_request.headers["Authorization"] == f"Bearer {JWT_TOKEN}"

    async def test_login_request_carries_the_mandatory_header_block(
        self, router: RecordingRouter
    ) -> None:
        """SmartAPI rejects a request missing any of these before it reaches a
        handler, so an omission surfaces as an opaque failure."""
        adapter = make_adapter(router)
        await adapter.authenticate()

        headers = router.requests[0].headers
        for required in (
            "X-UserType",
            "X-SourceID",
            "X-ClientLocalIP",
            "X-ClientPublicIP",
            "X-MACAddress",
            "X-PrivateKey",
        ):
            assert required in headers

    async def test_no_real_mac_address_is_harvested(
        self, router: RecordingRouter
    ) -> None:
        """The official SDK reads the host's real MAC. This does not.

        A broker client has no business fingerprinting the machine it runs on
        for a header the broker does not validate.
        """
        adapter = make_adapter(router)
        await adapter.authenticate()
        assert router.requests[0].headers["X-MACAddress"] == "00:00:00:00:00:00"

    async def test_invalid_totp_seed_fails_before_any_request(self) -> None:
        """A broker rejection reads as "your credentials are wrong", which
        sends an operator to check the PIN when the real fault is a mistyped
        seed."""
        routes = RecordingRouter()
        adapter = AngelOneAdapter(
            broker_settings(angel_one_totp_secret=SecretStr("not base32!")),
            transport=httpx.MockTransport(routes),
        )
        with pytest.raises(BrokerAuthenticationError):
            await adapter.authenticate()
        assert routes.requests == []

    async def test_a_login_response_missing_a_token_fails(self) -> None:
        """A session holding an empty feed token authenticates fine and then
        fails incomprehensibly the first time anything streams."""
        routes = RecordingRouter()
        routes.json_response(
            ROUTE_LOGIN, envelope({"jwtToken": "x", "refreshToken": "y"})
        )
        adapter = make_adapter(routes)
        with pytest.raises(BrokerDataError):
            await adapter.authenticate()

    async def test_logout_clears_tokens_even_when_the_call_fails(self) -> None:
        """Keeping a token because the logout request timed out means the next
        request uses a credential the broker may already have revoked."""
        routes = RecordingRouter()
        routes.json_response(ROUTE_LOGIN, envelope(LOGIN_DATA))
        routes.on(
            ROUTE_LOGOUT,
            lambda _: httpx.Response(500, json={"status": False}),
        )
        adapter = make_adapter(routes)
        await adapter.authenticate()

        await adapter.logout()  # must not raise
        assert adapter._auth.session is None


class TestReadOnlyEndpoints:
    async def test_funds_are_mapped_as_decimals(self, router: RecordingRouter) -> None:
        router.json_response(ROUTE_RMS_LIMIT, envelope(RMS_PAYLOAD))
        adapter = make_adapter(router)
        funds = await adapter.get_funds()

        assert isinstance(funds.net, Decimal)
        assert funds.available_cash == Decimal("20000.25")
        assert funds.retrieved_at is not None

    async def test_profile_is_mapped(self, router: RecordingRouter) -> None:
        router.json_response(
            ROUTE_PROFILE,
            envelope(
                {
                    "clientcode": "T0000001",
                    "name": "Test Account",
                    "exchanges": ["NSE", "NFO"],
                }
            ),
        )
        adapter = make_adapter(router)
        profile = await adapter.get_profile()
        assert profile.client_code == "T0000001"
        assert profile.exchanges == ("NSE", "NFO")


class TestHistoricalRequests:
    async def test_a_wide_range_becomes_several_conforming_requests(
        self, router: RecordingRouter
    ) -> None:
        """The planner's output, observed on the wire.

        Asking Angel One for a year of one-minute bars in one call is rejected
        outright, so this is the difference between working and not.
        """
        router.json_response(ROUTE_CANDLE_DATA, envelope([]))
        adapter = make_adapter(router)

        await adapter.get_historical_candles(
            NIFTY,
            Timeframe.M1,
            dt.datetime(2026, 1, 1, 9, 15, tzinfo=IST),
            dt.datetime(2026, 12, 31, 15, 30, tzinfo=IST),
        )
        assert len(router.bodies_for(ROUTE_CANDLE_DATA)) == 13

    async def test_range_bounds_are_sent_in_exchange_local_time(
        self, router: RecordingRouter
    ) -> None:
        """Angel One reads these strings as IST with no offset attached.

        Handing it a UTC wall clock asks for a window five and a half hours
        away from the one the caller meant — and gets back real bars from the
        wrong period.
        """
        router.json_response(ROUTE_CANDLE_DATA, envelope([]))
        adapter = make_adapter(router)

        # 03:45 UTC is 09:15 IST.
        await adapter.get_historical_candles(
            NIFTY,
            Timeframe.M5,
            dt.datetime(2026, 9, 25, 3, 45, tzinfo=dt.UTC),
            dt.datetime(2026, 9, 25, 10, 0, tzinfo=dt.UTC),
        )
        body = router.bodies_for(ROUTE_CANDLE_DATA)[0]
        assert body["fromdate"] == "2026-09-25 09:15"
        assert body["interval"] == "FIVE_MINUTE"

    async def test_candles_from_every_chunk_are_concatenated(
        self, router: RecordingRouter
    ) -> None:
        router.json_response(
            ROUTE_CANDLE_DATA,
            envelope(
                [["2026-09-25T09:15:00+05:30", "24000", "24050", "23990", "24020", "1"]]
            ),
        )
        adapter = make_adapter(router)
        candles = await adapter.get_historical_candles(
            NIFTY,
            Timeframe.M1,
            dt.datetime(2026, 1, 1, tzinfo=IST),
            dt.datetime(2026, 3, 1, tzinfo=IST),
        )
        assert len(candles) == len(router.bodies_for(ROUTE_CANDLE_DATA))
        assert all(c.timeframe is Timeframe.M1 for c in candles)

    async def test_greek_expiry_is_formatted_as_the_broker_expects(
        self, router: RecordingRouter
    ) -> None:
        router.json_response(ROUTE_OPTION_GREEK, envelope([]))
        adapter = make_adapter(router)
        await adapter.get_option_metrics("nifty", dt.datetime(2026, 1, 8, tzinfo=IST))
        body = router.bodies_for(ROUTE_OPTION_GREEK)[0]
        assert body["expirydate"] == "08JAN2026"
        assert body["name"] == "NIFTY"


class TestErrorTranslation:
    """Nothing above `app.brokers` should ever see an `httpx` exception."""

    async def test_a_timeout_becomes_a_network_error(self) -> None:
        routes = RecordingRouter()

        def timeout(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out")

        routes.on(ROUTE_LOGIN, timeout)
        adapter = make_adapter(routes)
        with pytest.raises(BrokerNetworkError):
            await adapter.authenticate()

    async def test_a_refused_connection_becomes_a_network_error(self) -> None:
        routes = RecordingRouter()

        def refused(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        routes.on(ROUTE_LOGIN, refused)
        adapter = make_adapter(routes)
        with pytest.raises(BrokerNetworkError):
            await adapter.authenticate()

    async def test_429_becomes_a_rate_limit_error_with_a_429_status(self) -> None:
        """Passed through so a caller can tell "slow down" from "this is
        broken" without parsing a message string."""
        routes = RecordingRouter()
        routes.on(ROUTE_LOGIN, lambda _: httpx.Response(429, text="slow down"))
        adapter = make_adapter(routes)
        with pytest.raises(BrokerRateLimitError) as caught:
            await adapter.authenticate()
        assert caught.value.status_code == 429

    async def test_a_5xx_becomes_unavailable_not_a_data_error(self) -> None:
        """A 503 may carry an HTML error page. Parsing it would report an
        outage as a malformed payload."""
        routes = RecordingRouter()
        routes.on(ROUTE_LOGIN, lambda _: httpx.Response(503, text="<html>down</html>"))
        adapter = make_adapter(routes)
        with pytest.raises(BrokerUnavailableError):
            await adapter.authenticate()

    async def test_a_non_json_200_becomes_a_data_error(self) -> None:
        routes = RecordingRouter()
        routes.on(ROUTE_LOGIN, lambda _: httpx.Response(200, text="not json"))
        adapter = make_adapter(routes)
        with pytest.raises(BrokerDataError):
            await adapter.authenticate()

    @pytest.mark.parametrize("code", ["AB1007", "AB1050"])
    async def test_credential_rejection_is_an_authentication_error(
        self, code: str
    ) -> None:
        routes = RecordingRouter()
        routes.json_response(ROUTE_LOGIN, envelope(None, status=False, errorcode=code))
        adapter = make_adapter(routes)
        with pytest.raises(BrokerAuthenticationError):
            await adapter.authenticate()

    async def test_authentication_errors_do_not_say_which_credential_failed(
        self,
    ) -> None:
        """The distinction between a wrong PIN and a wrong TOTP is useful to an
        attacker enumerating credentials and useless to an operator, who has to
        check both anyway."""
        routes = RecordingRouter()
        routes.json_response(
            ROUTE_LOGIN, envelope(None, status=False, errorcode="AB1050")
        )
        adapter = make_adapter(routes)
        with pytest.raises(BrokerAuthenticationError) as caught:
            await adapter.authenticate()
        message = caught.value.message.lower()
        assert "totp" not in message
        assert "pin" not in message

    async def test_an_unrecognised_code_is_not_guessed_at(self) -> None:
        """Picking a plausible category would send a caller down a recovery
        path chosen at random. The specific code goes to the log instead."""
        routes = RecordingRouter()
        routes.json_response(
            ROUTE_LOGIN, envelope(None, status=False, errorcode="AB9999")
        )
        adapter = make_adapter(routes)
        with pytest.raises(BrokerError) as caught:
            await adapter.authenticate()
        assert type(caught.value) is BrokerError

    async def test_the_camelcase_error_key_is_also_read(self) -> None:
        """`getMarketData` spells it `errorCode`. An error that goes
        unrecognised because of a capital letter is reported as a data fault."""
        routes = RecordingRouter()
        routes.json_response(
            ROUTE_LOGIN,
            {
                "status": False,
                "message": "Token Expired",
                "errorCode": "AB1050",
                "data": None,
            },
        )
        adapter = make_adapter(routes)
        with pytest.raises(BrokerAuthenticationError):
            await adapter.authenticate()


class TestSessionRecovery:
    async def test_an_expired_session_is_refreshed_exactly_once(self) -> None:
        """Angel One tokens die at midnight IST, so one refresh covers the
        expected daily case."""
        routes = RecordingRouter()
        routes.json_response(ROUTE_LOGIN, envelope(LOGIN_DATA))
        routes.json_response(
            "/rest/auth/angelbroking/jwt/v1/generateTokens", envelope(LOGIN_DATA)
        )
        routes.sequence(
            ROUTE_RMS_LIMIT,
            [
                envelope(None, status=False, errorcode="AG8002"),
                envelope(RMS_PAYLOAD),
            ],
        )
        adapter = make_adapter(routes)
        funds = await adapter.get_funds()

        assert funds.available_cash == Decimal("20000.25")
        assert (
            routes.paths().count("/rest/auth/angelbroking/jwt/v1/generateTokens") == 1
        )

    async def test_a_second_expiry_propagates_rather_than_looping(self) -> None:
        """A retry loop against a login endpoint limited to one call per second
        is how a transient problem becomes a locked account."""
        from app.brokers.exceptions import BrokerSessionExpiredError

        routes = RecordingRouter()
        routes.json_response(ROUTE_LOGIN, envelope(LOGIN_DATA))
        routes.json_response(
            "/rest/auth/angelbroking/jwt/v1/generateTokens", envelope(LOGIN_DATA)
        )
        routes.json_response(
            ROUTE_RMS_LIMIT, envelope(None, status=False, errorcode="AG8002")
        )
        adapter = make_adapter(routes)

        with pytest.raises(BrokerSessionExpiredError):
            await adapter.get_funds()
        assert routes.paths().count(ROUTE_RMS_LIMIT) == 2
