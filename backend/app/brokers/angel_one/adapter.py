"""The Angel One implementation of `BrokerAdapter`.

Composition, not inheritance: this class owns a transport, an authenticator and
a set of mapping functions, and its own body is mostly the wiring between them.
That is deliberate — the interesting logic (classifying an error, refusing a
malformed price, splitting a date range) is in modules that can be tested
without constructing an adapter at all.

READ-ONLY, STRUCTURALLY
-----------------------
There is no order-placement method here, because there is no order-placement
route in `constants` and no order-placement member on the Protocol. The
guarantee is not a flag that could be flipped or a check that could be
bypassed; it is the absence of any code that could transmit an order.

`get_order_book` and `get_trade_book` read orders placed by other means. That
is a window, not a lever.

SESSION HANDLING
----------------
Every data call goes through `_call`, which authenticates first and retries
exactly once on a session expiry. Once — not a loop. Angel One tokens die at
midnight IST, so a single refresh covers the expected daily case; if the second
attempt also reports an expired session, something is wrong that retrying will
not fix, and hammering a login endpoint limited to one call per second is how a
transient problem becomes a locked account.
"""

from __future__ import annotations

import datetime as dt
from types import TracebackType
from typing import Any, Self

import httpx

from app.brokers.angel_one import mapper
from app.brokers.angel_one.auth import AngelOneAuthenticator
from app.brokers.angel_one.client import AngelOneHttpClient
from app.brokers.angel_one.constants import (
    CANDLE_DATETIME_FORMAT,
    ROUTE_CANDLE_DATA,
    ROUTE_LTP,
    ROUTE_OI_DATA,
    ROUTE_OPTION_GREEK,
    ROUTE_ORDER_BOOK,
    ROUTE_POSITIONS,
    ROUTE_PROFILE,
    ROUTE_RMS_LIMIT,
    ROUTE_TRADE_BOOK,
    TIMEFRAME_TO_INTERVAL,
)
from app.brokers.angel_one.history import plan_history_requests
from app.brokers.exceptions import (
    BrokerConfigurationError,
    BrokerDataError,
    BrokerSessionExpiredError,
)
from app.brokers.models import (
    BrokerFunds,
    BrokerInstrument,
    BrokerOrder,
    BrokerPosition,
    BrokerProfile,
    BrokerQuote,
    BrokerSession,
    BrokerTrade,
    Candle,
    OpenInterestObservation,
    OptionMetrics,
)
from app.core.config import Settings
from app.core.constants import IST
from app.core.logging import get_logger
from app.domain.enums import Timeframe

logger = get_logger(__name__)

#: Month names for the `DDMMMYYYY` expiry format `optionGreek` expects.
#:
#: Hard-coded rather than produced by `strftime("%b")`, which is
#: locale-sensitive: on a host with a non-English locale the same call yields a
#: month name Angel One does not recognise, and the failure appears only in
#: that one deployment.
_MONTH_ABBREVIATIONS = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)  # fmt: skip


class AngelOneAdapter:
    """Read-only access to one Angel One account.

    Satisfies `app.brokers.base.BrokerAdapter` structurally. It does not
    inherit from it, which is the point of a Protocol: conformance is checked
    by the type checker rather than asserted by a base class.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Construct an adapter for a configured account.

        Raises `BrokerConfigurationError` when credentials are incomplete,
        rather than constructing an object that cannot do anything. The
        alternative — a half-built adapter that fails on first use — pushes the
        error to a point where the cause is much harder to see.
        """
        # The API key is re-checked explicitly rather than relying on
        # `angel_one_configured`, because mypy cannot narrow an Optional
        # through a property. An `assert` would satisfy the type checker but
        # vanishes under `python -O`, leaving a `None` to reach the header
        # builder — so the narrowing is a real runtime check.
        if not settings.angel_one_configured or settings.angel_one_api_key is None:
            raise BrokerConfigurationError()

        self._settings = settings
        self._client = AngelOneHttpClient(
            api_key=settings.angel_one_api_key.get_secret_value(),
            timeout=settings.angel_one_timeout,
            client_public_ip=settings.angel_one_primary_static_ip,
            transport=transport,
        )
        self._auth = AngelOneAuthenticator(settings, self._client)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Release the HTTP connection pool.

        Does not log out. Ending the broker session and closing a socket are
        different decisions: a process restarting in five seconds should keep
        its token, and discarding it would burn a login against a one-per-
        second limit for no reason.
        """
        await self._client.aclose()

    # -- Session ------------------------------------------------------------

    @property
    def session(self) -> BrokerSession | None:
        """The current session, or `None`, without attempting to create one.

        Not part of `BrokerAdapter`: the Protocol is about *doing* things with a
        broker, and a caller that needs a session should call `authenticate`.
        This exists for the status endpoint, whose entire job is to answer "are
        we connected?" — and which must be able to answer "no" without a login
        attempt, because reporting that the integration is unconfigured is the
        one case where it matters most.
        """
        return self._auth.session

    async def authenticate(self) -> BrokerSession:
        return await self._auth.authenticate()

    async def logout(self) -> None:
        await self._auth.logout()

    async def _call(
        self,
        method: str,
        route: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Authenticated request with exactly one session-expiry retry."""
        await self._auth.authenticate()
        try:
            return await self._client.request(method, route, json=json, params=params)
        except BrokerSessionExpiredError:
            logger.info("Angel One session expired mid-request; refreshing once")
            await self._auth.refresh()
            # Any failure from here propagates. A second expiry is not a
            # transient event, and a retry loop against a login endpoint is a
            # good way to turn one bad request into a locked account.
            return await self._client.request(method, route, json=json, params=params)

    # -- Account ------------------------------------------------------------

    async def get_profile(self) -> BrokerProfile:
        return mapper.map_profile(await self._call("GET", ROUTE_PROFILE))

    async def get_funds(self) -> BrokerFunds:
        payload = await self._call("GET", ROUTE_RMS_LIMIT)
        # The timestamp is ours, not the broker's: `getRMS` carries no `asof`
        # field, so this records when *we* observed the figures. Labelling it
        # as the broker's own would claim a precision that does not exist.
        return mapper.map_funds(payload, retrieved_at=dt.datetime.now(tz=IST))

    async def get_positions(self) -> list[BrokerPosition]:
        return mapper.map_positions(await self._call("GET", ROUTE_POSITIONS))

    async def get_order_book(self) -> list[BrokerOrder]:
        return mapper.map_order_book(await self._call("GET", ROUTE_ORDER_BOOK))

    async def get_trade_book(self) -> list[BrokerTrade]:
        return mapper.map_trade_book(await self._call("GET", ROUTE_TRADE_BOOK))

    # -- Market data --------------------------------------------------------

    async def get_ltp(self, instrument: BrokerInstrument) -> BrokerQuote:
        payload = await self._call(
            "POST",
            ROUTE_LTP,
            json={
                "exchange": instrument.exchange_segment,
                "tradingsymbol": instrument.symbol,
                "symboltoken": instrument.token,
            },
        )
        data = mapper.require_mapping(payload, "getLtpData")
        return BrokerQuote(
            token=instrument.token,
            exchange_segment=instrument.exchange_segment,
            last_traded_price=mapper.parse_decimal(data.get("ltp"), "ltp"),
            symbol=mapper.optional_str(data, "tradingsymbol") or instrument.symbol,
            open=mapper.parse_optional_decimal(data.get("open"), "open"),
            high=mapper.parse_optional_decimal(data.get("high"), "high"),
            low=mapper.parse_optional_decimal(data.get("low"), "low"),
            close=mapper.parse_optional_decimal(data.get("close"), "close"),
        )

    async def get_historical_candles(
        self,
        instrument: BrokerInstrument,
        timeframe: Timeframe,
        start: dt.datetime,
        end: dt.datetime,
    ) -> list[Candle]:
        """Fetch OHLCV bars across an arbitrary range, ascending.

        The range is split into broker-sized chunks and the results
        concatenated. Chunks are requested in order and their results are
        already ascending, so the concatenation is sorted without a re-sort —
        but the results are *not* deduplicated or gap-filled. A weekend, a
        holiday or a contract that had not yet listed produces fewer bars than
        a naive count expects, and inventing bars to cover the difference would
        put fabricated prices in a market-data table.
        """
        interval = self._interval_for(timeframe)
        candles: list[Candle] = []
        for chunk in plan_history_requests(timeframe, start, end):
            payload = await self._call(
                "POST",
                ROUTE_CANDLE_DATA,
                json={
                    "exchange": instrument.exchange_segment,
                    "symboltoken": instrument.token,
                    "interval": interval,
                    "fromdate": _format_range_bound(chunk.start),
                    "todate": _format_range_bound(chunk.end),
                },
            )
            candles.extend(mapper.map_candles(payload, timeframe))
        return candles

    async def get_historical_oi(
        self,
        instrument: BrokerInstrument,
        timeframe: Timeframe,
        start: dt.datetime,
        end: dt.datetime,
    ) -> list[OpenInterestObservation]:
        """Fetch open-interest history for one F&O contract, ascending.

        Only live contracts have this. An expired instrument returns an empty
        list, which is a fact about the contract rather than a failure and is
        reported as such.
        """
        interval = self._interval_for(timeframe)
        observations: list[OpenInterestObservation] = []
        for chunk in plan_history_requests(timeframe, start, end):
            payload = await self._call(
                "POST",
                ROUTE_OI_DATA,
                json={
                    "exchange": instrument.exchange_segment,
                    "symboltoken": instrument.token,
                    "interval": interval,
                    "fromdate": _format_range_bound(chunk.start),
                    "todate": _format_range_bound(chunk.end),
                },
            )
            observations.extend(mapper.map_open_interest(payload))
        return observations

    async def get_option_metrics(
        self, underlying: str, expiry: dt.datetime
    ) -> list[OptionMetrics]:
        payload = await self._call(
            "POST",
            ROUTE_OPTION_GREEK,
            json={
                "name": underlying.upper(),
                "expirydate": _format_greek_expiry(expiry.date()),
            },
        )
        return mapper.map_option_greeks(payload)

    @staticmethod
    def _interval_for(timeframe: Timeframe) -> str:
        """This system's timeframe as Angel One's interval name.

        A timeframe with no mapping fails rather than falling back to a
        neighbouring interval. Serving five-minute bars to a caller that asked
        for one-minute is a wrong answer delivered with full confidence — every
        value in it is a real price, and nothing downstream could detect the
        substitution.
        """
        interval = TIMEFRAME_TO_INTERVAL.get(timeframe)
        if interval is None:
            raise BrokerDataError(
                f"Angel One has no interval for the '{timeframe.value}' timeframe."
            )
        return interval


def _format_range_bound(moment: dt.datetime) -> str:
    """Format a bound as `YYYY-MM-DD HH:MM` in exchange-local time.

    Converted to IST first. Angel One interprets these strings as exchange
    time with no offset attached, so handing it a UTC wall clock asks for a
    window five and a half hours away from the one the caller meant — and gets
    back real bars from the wrong period.
    """
    return moment.astimezone(IST).strftime(CANDLE_DATETIME_FORMAT)


def _format_greek_expiry(expiry: dt.date) -> str:
    """Format an expiry as `25JAN2024`."""
    return f"{expiry.day:02d}{_MONTH_ABBREVIATIONS[expiry.month - 1]}{expiry.year}"
