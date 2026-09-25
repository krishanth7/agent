"""Every Angel One-specific literal, in one place.

WHY A CONSTANTS MODULE AT ALL
-----------------------------
A route string or an interval name written inline is a value that cannot be
tested, cannot be grepped for reliably, and will eventually be written twice
with a typo in one of them. Collecting them here makes the vendor surface
enumerable: the full set of things that must change when Angel One changes
something is exactly the contents of this file.

PROVENANCE
----------
Values here were taken from the published SmartAPI documentation and the
official `smartapi-python` SDK during Phase 3 research. Where the two sources
disagree, or where the documentation is silent, the discrepancy is marked
UNVERIFIED in a comment rather than resolved by guessing. An UNVERIFIED value
is one that must be confirmed against a live account before anything depends
on it for money.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import Final

from app.domain.enums import Timeframe

# -- Endpoints --------------------------------------------------------------

API_ROOT: Final = "https://apiconnect.angelone.in"

#: Published outside the API host, and unauthenticated. It is a ~40 MB JSON
#: document listing every tradable contract, regenerated each morning before
#: the session. Not a REST endpoint and not rate-limited alongside one.
SCRIP_MASTER_URL: Final = (
    "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
)

ROUTE_LOGIN: Final = "/rest/auth/angelbroking/user/v1/loginByPassword"
ROUTE_GENERATE_TOKENS: Final = "/rest/auth/angelbroking/jwt/v1/generateTokens"
ROUTE_LOGOUT: Final = "/rest/secure/angelbroking/user/v1/logout"
ROUTE_PROFILE: Final = "/rest/secure/angelbroking/user/v1/getProfile"
ROUTE_RMS_LIMIT: Final = "/rest/secure/angelbroking/user/v1/getRMS"
ROUTE_POSITIONS: Final = "/rest/secure/angelbroking/order/v1/getPosition"
ROUTE_ORDER_BOOK: Final = "/rest/secure/angelbroking/order/v1/getOrderBook"
ROUTE_TRADE_BOOK: Final = "/rest/secure/angelbroking/order/v1/getTradeBook"
ROUTE_SEARCH_SCRIP: Final = "/rest/secure/angelbroking/order/v1/searchScrip"
ROUTE_LTP: Final = "/rest/secure/angelbroking/order/v1/getLtpData"
ROUTE_MARKET_DATA: Final = "/rest/secure/angelbroking/market/v1/quote/"
ROUTE_CANDLE_DATA: Final = "/rest/secure/angelbroking/historical/v1/getCandleData"
ROUTE_OI_DATA: Final = "/rest/secure/angelbroking/historical/v1/getOIData"
ROUTE_OPTION_GREEK: Final = "/rest/secure/angelbroking/marketData/v1/optionGreek"

#: Order-placement routes are deliberately absent. See `app.brokers.base`:
#: a route constant is the first half of a call site, and this system has
#: neither half.

WEBSOCKET_URL: Final = "wss://smartapisocket.angelone.in/smart-stream"
ORDER_UPDATE_WEBSOCKET_URL: Final = "wss://tns.angelone.in/smart-order-update"


# -- Wire formats -----------------------------------------------------------

#: `getCandleData` and `getOIData` both want this, and neither accepts an ISO
#: string. Minute precision only — there is no seconds component.
CANDLE_DATETIME_FORMAT: Final = "%Y-%m-%d %H:%M"

#: `optionGreek` wants `25JAN2024`. Upper-cased explicitly at the call site,
#: because `%b` is locale-sensitive and renders title-case on most systems.
GREEK_EXPIRY_FORMAT: Final = "%d%b%Y"

#: The exchange's own zone. Every timestamp Angel One returns carries a
#: `+05:30` offset and every one it accepts is interpreted in this zone.
EXCHANGE_TIMEZONE: Final = "Asia/Kolkata"


# -- Vocabularies -----------------------------------------------------------


class AngelExchange(StrEnum):
    """Exchange/segment codes as Angel One spells them in REST payloads."""

    NSE = "NSE"
    NFO = "NFO"
    BSE = "BSE"
    BFO = "BFO"
    MCX = "MCX"
    CDS = "CDS"
    NCDEX = "NCDEX"


class AngelFeedExchangeType(IntEnum):
    """Numeric segment codes used by the binary streaming protocol.

    Different from `AngelExchange` and not derivable from it — the websocket
    speaks integers, the REST API speaks strings, and they do not even cover
    the same set. Mapping between them is `EXCHANGE_TO_FEED_TYPE` below.
    """

    NSE_CM = 1
    NSE_FO = 2
    BSE_CM = 3
    BSE_FO = 4
    MCX_FO = 5
    NCX_FO = 7
    CDE_FO = 13


EXCHANGE_TO_FEED_TYPE: Final[MappingProxyType[AngelExchange, AngelFeedExchangeType]] = (
    MappingProxyType(
        {
            AngelExchange.NSE: AngelFeedExchangeType.NSE_CM,
            AngelExchange.NFO: AngelFeedExchangeType.NSE_FO,
            AngelExchange.BSE: AngelFeedExchangeType.BSE_CM,
            AngelExchange.BFO: AngelFeedExchangeType.BSE_FO,
            AngelExchange.MCX: AngelFeedExchangeType.MCX_FO,
            AngelExchange.NCDEX: AngelFeedExchangeType.NCX_FO,
            AngelExchange.CDS: AngelFeedExchangeType.CDE_FO,
        }
    )
)


class AngelFeedMode(IntEnum):
    """How much the stream sends per tick.

    LTP is one price. QUOTE adds volume, OHLC and totals. SNAP_QUOTE adds
    circuit limits, 52-week range and five levels of depth.

    DEPTH is present in the SDK but absent from the published mode table, and
    its payload layout is UNVERIFIED. Nothing subscribes to it.
    """

    LTP = 1
    QUOTE = 2
    SNAP_QUOTE = 3
    DEPTH = 4


class AngelFeedAction(IntEnum):
    """Subscription verbs. Note `UNSUBSCRIBE` is 0, not 2."""

    UNSUBSCRIBE = 0
    SUBSCRIBE = 1


#: Streamed prices are integers in paise. Dividing by this — as `Decimal`, and
#: never as float — is the single most consequential line in the tick decoder:
#: get it wrong and every price is off by two orders of magnitude in a way that
#: still looks like a plausible number.
FEED_PRICE_DIVISOR: Final = 100

#: The server closes a connection that has not spoken for roughly a minute.
#: Ten seconds gives five chances to miss one before that happens.
FEED_HEARTBEAT_SECONDS: Final = 10
FEED_HEARTBEAT_MESSAGE: Final = "ping"

#: Documented ceiling on tokens across all subscriptions on one connection.
FEED_MAX_TOKENS: Final = 1000

#: Documented ceiling on concurrent order-update connections per client.
ORDER_UPDATE_MAX_CONNECTIONS: Final = 3


# -- Historical intervals ---------------------------------------------------

#: Our `Timeframe` to Angel One's interval name.
#:
#: This mapping exists exactly once. An interval name written anywhere else is
#: a second source of truth, and the failure it produces — a silently wrong
#: aggregation — is invisible in a response that otherwise looks correct.
#:
#: Angel One also publishes `TEN_MINUTE`. There is deliberately no `10m` in our
#: `Timeframe`: adding a member means altering the CHECK constraint on
#: `ohlcv_candles.timeframe` by migration, and nothing in this system requests
#: ten-minute bars. The omission is a decision, not an oversight; if a caller
#: ever needs them, add `M10` to the enum and migrate the constraint together.
TIMEFRAME_TO_INTERVAL: Final[MappingProxyType[Timeframe, str]] = MappingProxyType(
    {
        Timeframe.M1: "ONE_MINUTE",
        Timeframe.M3: "THREE_MINUTE",
        Timeframe.M5: "FIVE_MINUTE",
        Timeframe.M15: "FIFTEEN_MINUTE",
        Timeframe.M30: "THIRTY_MINUTE",
        Timeframe.H1: "ONE_HOUR",
        Timeframe.D1: "ONE_DAY",
    }
)

#: Maximum days of history Angel One will return in a single request, by
#: interval. Exceeding it is rejected outright rather than truncated, so a
#: caller asking for a year of one-minute bars must be split into chunks — see
#: the range planner in `app.brokers.angel_one.history`.
#:
#: The numbers are the broker's, not a safety margin of ours. They are days of
#: *calendar* span, not trading days.
INTERVAL_MAX_DAYS: Final[MappingProxyType[Timeframe, int]] = MappingProxyType(
    {
        Timeframe.M1: 30,
        Timeframe.M3: 60,
        Timeframe.M5: 100,
        Timeframe.M15: 200,
        Timeframe.M30: 200,
        Timeframe.H1: 400,
        Timeframe.D1: 2000,
    }
)


# -- Error codes ------------------------------------------------------------

#: Codes meaning "the session is gone" — recoverable by re-authenticating.
#:
#: Distinguished from credential failures because the response is different:
#: these warrant one silent refresh, whereas a rejected PIN warrants stopping
#: and telling an operator. `AB1010` and `AB1011` are worded as login errors
#: but are returned for an expired session, which is why they are here.
SESSION_ERROR_CODES: Final[frozenset[str]] = frozenset(
    {
        "AG8001",  # Invalid Token
        "AG8002",  # Token Expired
        "AG8003",  # Token missing
        "AB8050",  # Invalid Refresh Token
        "AB8051",  # Refresh Token Expired
        "AB1010",  # AMX Session Expired
        "AB1011",  # Client not login
    }
)

#: Codes meaning the credentials themselves were rejected.
#:
#: `AB1007` is listed by Angel One's own login documentation as the invalid
#: credential response, but community reports also see it for an expired token
#: and for an MPIN-attempt lockout. It is classified as authentication here
#: because that is the reading that fails *safely*: treating a genuine lockout
#: as a refreshable session would drive a retry loop straight into the lockout
#: that produced it.
AUTHENTICATION_ERROR_CODES: Final[frozenset[str]] = frozenset(
    {
        "AB1007",  # Invalid client code / MPIN / API key, or account locked
        "AB1050",  # Invalid TOTP
    }
)

#: Codes meaning the broker had a transient problem of its own.
#:
#: `AB1004` and `AB2001` both surface as "please try after sometime". They are
#: broker-side faults, not anything the caller did, so they map to
#: `BrokerUnavailableError` and a bounded retry is reasonable.
UNAVAILABLE_ERROR_CODES: Final[frozenset[str]] = frozenset(
    {
        "AB1004",
        "AB2001",
    }
)

#: There is deliberately no authorization or rate-limit code set.
#:
#: An earlier draft of this file had both, populated from plausible-looking
#: guesses; checking them found three of five were simply wrong — `AB1004` is a
#: transient broker fault rather than a permission denial, and `AB1018` is
#: "failed to get symbol details" rather than "exchange not enabled". Inventing
#: a mapping is worse than having none, because a wrong classification sends
#: the caller down a recovery path that cannot work.
#:
#: Throttling and permission failures are therefore classified from the HTTP
#: status instead, which the transport layer can read without interpretation.
#: If the official code list is confirmed later, add the sets here.

#: The envelope key is `errorcode` on most endpoints but `errorCode` on
#: `getMarketData`. Both are read, because an error that goes unrecognised
#: because of a capital letter is an error reported as a data fault.
ERROR_CODE_KEYS: Final[tuple[str, ...]] = ("errorcode", "errorCode")


# -- Rate limits ------------------------------------------------------------

#: Published per-endpoint limits, requests per second. These are the broker's
#: figures; nothing here enforces them yet, and a limiter added later must read
#: from this table rather than restating it.
#:
#: `getOIData` and `putCallRatio` do not appear in the published table at all.
#: Their limits are UNVERIFIED and are assumed to match the other historical
#: endpoints until confirmed — the conservative direction to guess in.
RATE_LIMIT_PER_SECOND: Final[MappingProxyType[str, int]] = MappingProxyType(
    {
        ROUTE_LOGIN: 1,
        ROUTE_PROFILE: 3,
        ROUTE_RMS_LIMIT: 2,
        ROUTE_ORDER_BOOK: 1,
        ROUTE_TRADE_BOOK: 1,
        ROUTE_POSITIONS: 1,
        ROUTE_SEARCH_SCRIP: 1,
        ROUTE_LTP: 10,
        ROUTE_MARKET_DATA: 10,
        ROUTE_CANDLE_DATA: 3,
        ROUTE_OI_DATA: 3,  # UNVERIFIED — assumed equal to getCandleData
        ROUTE_OPTION_GREEK: 1,
    }
)
