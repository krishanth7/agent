"""Angel One payloads to broker-neutral records.

This module is where the vendor's vocabulary stops. Above it, nothing knows
that funds arrive under `availablecash`, that every number is a string, or that
`m2munrealized` is spelled without a separator.

THE RULE THIS FILE EXISTS TO ENFORCE
------------------------------------
A field that cannot be parsed fails the request. It does not become `0`, it
does not become `None`, and it is not skipped with a warning.

This is not pedantry. A price that silently defaults to zero is
indistinguishable from a real one two layers up: it has the right type, it
serializes, it renders, and it lands in the database looking exactly like a
genuine observation. By the time anyone notices the P&L is wrong, the bad row
has been aggregated into a month of history and there is no way to tell which
figures were real. Failing loudly costs one request. Defaulting quietly costs
the integrity of the whole dataset.

The one sanctioned use of `None` is a field the broker genuinely did not send —
an optional one, absent from the payload. That is a fact ("unknown"), not a
substitution ("zero").
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Any

from app.brokers.angel_one.constants import EXCHANGE_TIMEZONE
from app.brokers.exceptions import BrokerDataError
from app.brokers.models import (
    BrokerFunds,
    BrokerOrder,
    BrokerPosition,
    BrokerProfile,
    BrokerTrade,
    Candle,
    OpenInterestObservation,
    OptionMetrics,
)
from app.domain.enums import OptionType, Timeframe

_EXCHANGE_TZ = dt.timezone(dt.timedelta(hours=5, minutes=30), EXCHANGE_TIMEZONE)


def require_mapping(payload: object, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise BrokerDataError(
            f"Angel One returned {type(payload).__name__} rather than an "
            f"object for {context}."
        )
    return payload


def _require_list(payload: object, context: str) -> list[Any]:
    """Coerce a book-style payload to a list.

    Angel One returns `null` rather than `[]` for an empty order book, trade
    book or position list. That is emptiness, not absence: a flat account has
    no positions and saying so is a correct answer, not a fault.
    """
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise BrokerDataError(
            f"Angel One returned {type(payload).__name__} rather than a list "
            f"for {context}."
        )
    return payload


def parse_decimal(value: object, field: str) -> Decimal:
    """Required decimal. Raises rather than defaulting.

    Constructed from `str(value)` so that a float which somehow reached here
    is stringified before conversion — `Decimal(0.1)` captures the binary
    approximation, `Decimal("0.1")` is the value that was meant.

    An empty string is rejected. Angel One uses `""` for "not applicable" on
    some fields, and treating that as zero on a *required* one would be the
    exact silent-default failure this module exists to prevent.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        raise BrokerDataError(f"Angel One omitted the required field '{field}'.")
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise BrokerDataError(
            f"Angel One sent an unparseable number for '{field}'."
        ) from exc


def parse_optional_decimal(value: object, field: str) -> Decimal | None:
    """Optional decimal. Absent stays absent; malformed still fails.

    The asymmetry is deliberate. A missing optional field is information the
    broker chose not to send. A *present* field that will not parse is a broken
    contract, and swallowing it would hide a real change in the API behind a
    `None` that looks routine.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return parse_decimal(value, field)


def parse_int(value: object, field: str) -> int:
    """Required integer, via `Decimal` so `"100.0"` is accepted.

    Brokers send quantities as decimal strings. `int("100.0")` raises, so the
    value goes through `Decimal` first — but a genuinely fractional quantity is
    rejected rather than truncated, because no exchange trades a third of a
    contract and a value that claims otherwise means something upstream is
    wrong.
    """
    number = parse_decimal(value, field)
    if number != number.to_integral_value():
        raise BrokerDataError(
            f"Angel One sent a fractional value for the integer field '{field}'."
        )
    return int(number)


def parse_optional_int(value: object, field: str) -> int | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return parse_int(value, field)


def require_str(payload: dict[str, Any], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BrokerDataError(f"Angel One omitted '{key}' in {context}.")
    return value.strip()


def optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def parse_exchange_timestamp(value: object, field: str) -> dt.datetime:
    """Parse an Angel One timestamp into an aware datetime.

    Angel One's historical endpoints return ISO-8601 with an explicit `+05:30`
    offset. `fromisoformat` handles that natively. A value that arrives without
    an offset is *assumed* to be exchange-local rather than UTC — which is the
    documented behaviour, and the assumption is made explicit here rather than
    left to whatever the host timezone happens to be.

    The result is always aware. A naive datetime in a market-data table is a
    bug waiting for the first reader who assumes it is UTC.
    """
    if not isinstance(value, str) or not value.strip():
        raise BrokerDataError(f"Angel One omitted the timestamp field '{field}'.")
    try:
        parsed = dt.datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise BrokerDataError(
            f"Angel One sent an unparseable timestamp for '{field}'."
        ) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=_EXCHANGE_TZ)
    return parsed


# -- Account ----------------------------------------------------------------


def map_profile(payload: object) -> BrokerProfile:
    data = require_mapping(payload, "getProfile")
    exchanges = data.get("exchanges")
    return BrokerProfile(
        client_code=require_str(data, "clientcode", "getProfile"),
        name=optional_str(data, "name"),
        email=optional_str(data, "email"),
        broker_name=optional_str(data, "broker"),
        exchanges=(
            tuple(str(item) for item in exchanges if item)
            if isinstance(exchanges, list)
            else ()
        ),
    )


def map_funds(payload: object, *, retrieved_at: dt.datetime) -> BrokerFunds:
    """Map an `getRMS` response.

    `net`, `availablecash` and `utiliseddebits` are required: an account
    summary missing any of the three is not a summary, and rendering a balance
    of zero because a field was absent would be a lie about someone's money.
    Every component of the margin breakdown below them is optional, because not
    every account type reports every component.
    """
    data = require_mapping(payload, "getRMS")
    return BrokerFunds(
        net=parse_decimal(data.get("net"), "net"),
        available_cash=parse_decimal(data.get("availablecash"), "availablecash"),
        used_margin=parse_decimal(data.get("utiliseddebits"), "utiliseddebits"),
        available_intraday_payin=parse_optional_decimal(
            data.get("availableintradaypayin"), "availableintradaypayin"
        ),
        available_limit_margin=parse_optional_decimal(
            data.get("availablelimitmargin"), "availablelimitmargin"
        ),
        collateral=parse_optional_decimal(data.get("collateral"), "collateral"),
        unrealized_mtm=parse_optional_decimal(
            data.get("m2munrealized"), "m2munrealized"
        ),
        realized_mtm=parse_optional_decimal(data.get("m2mrealized"), "m2mrealized"),
        utilised_span=parse_optional_decimal(data.get("utilisedspan"), "utilisedspan"),
        utilised_option_premium=parse_optional_decimal(
            data.get("utilisedoptionpremium"), "utilisedoptionpremium"
        ),
        utilised_exposure=parse_optional_decimal(
            data.get("utilisedexposure"), "utilisedexposure"
        ),
        utilised_holding_sales=parse_optional_decimal(
            data.get("utilisedholdingsales"), "utilisedholdingsales"
        ),
        utilised_turnover=parse_optional_decimal(
            data.get("utilisedturnover"), "utilisedturnover"
        ),
        utilised_payout=parse_optional_decimal(
            data.get("utilisedpayout"), "utilisedpayout"
        ),
        retrieved_at=retrieved_at,
    )


def map_positions(payload: object) -> list[BrokerPosition]:
    rows = _require_list(payload, "getPosition")
    return [_map_position(require_mapping(row, "getPosition")) for row in rows]


def _map_position(data: dict[str, Any]) -> BrokerPosition:
    return BrokerPosition(
        symbol=require_str(data, "tradingsymbol", "getPosition"),
        token=require_str(data, "symboltoken", "getPosition"),
        exchange_segment=require_str(data, "exchange", "getPosition"),
        product_type=require_str(data, "producttype", "getPosition"),
        net_quantity=parse_int(data.get("netqty"), "netqty"),
        buy_quantity=parse_optional_int(data.get("buyqty"), "buyqty"),
        sell_quantity=parse_optional_int(data.get("sellqty"), "sellqty"),
        average_price=parse_optional_decimal(data.get("avgnetprice"), "avgnetprice"),
        last_traded_price=parse_optional_decimal(data.get("ltp"), "ltp"),
        realized_pnl=parse_optional_decimal(data.get("realised"), "realised"),
        unrealized_pnl=parse_optional_decimal(data.get("unrealised"), "unrealised"),
        lot_size=parse_optional_int(data.get("lotsize"), "lotsize"),
    )


def map_order_book(payload: object) -> list[BrokerOrder]:
    rows = _require_list(payload, "getOrderBook")
    return [_map_order(require_mapping(row, "getOrderBook")) for row in rows]


def _map_order(data: dict[str, Any]) -> BrokerOrder:
    """Map one order-book row.

    `status`, `ordertype` and `transactiontype` stay as the broker's own
    strings. Coercing them into this system's `OrderStatus` / `OrderType`
    enums would mean picking a nearest member for anything unrecognised, and
    an order's state is not something to approximate.
    """
    return BrokerOrder(
        order_id=require_str(data, "orderid", "getOrderBook"),
        symbol=require_str(data, "tradingsymbol", "getOrderBook"),
        token=require_str(data, "symboltoken", "getOrderBook"),
        exchange_segment=require_str(data, "exchange", "getOrderBook"),
        transaction_type=require_str(data, "transactiontype", "getOrderBook"),
        order_type=require_str(data, "ordertype", "getOrderBook"),
        product_type=require_str(data, "producttype", "getOrderBook"),
        status=require_str(data, "status", "getOrderBook"),
        quantity=parse_int(data.get("quantity"), "quantity"),
        filled_quantity=parse_optional_int(data.get("filledshares"), "filledshares"),
        price=parse_optional_decimal(data.get("price"), "price"),
        trigger_price=parse_optional_decimal(data.get("triggerprice"), "triggerprice"),
        average_price=parse_optional_decimal(data.get("averageprice"), "averageprice"),
        order_timestamp=_optional_timestamp(data.get("updatetime"), "updatetime"),
        status_message=optional_str(data, "text"),
    )


def map_trade_book(payload: object) -> list[BrokerTrade]:
    rows = _require_list(payload, "getTradeBook")
    return [_map_trade(require_mapping(row, "getTradeBook")) for row in rows]


def _map_trade(data: dict[str, Any]) -> BrokerTrade:
    return BrokerTrade(
        trade_id=require_str(data, "fillid", "getTradeBook"),
        order_id=require_str(data, "orderid", "getTradeBook"),
        symbol=require_str(data, "tradingsymbol", "getTradeBook"),
        token=require_str(data, "symboltoken", "getTradeBook"),
        exchange_segment=require_str(data, "exchange", "getTradeBook"),
        transaction_type=require_str(data, "transactiontype", "getTradeBook"),
        product_type=require_str(data, "producttype", "getTradeBook"),
        quantity=parse_int(data.get("fillsize"), "fillsize"),
        price=parse_decimal(data.get("fillprice"), "fillprice"),
        trade_timestamp=_optional_timestamp(data.get("filltime"), "filltime"),
    )


def _optional_timestamp(value: object, field: str) -> dt.datetime | None:
    """Best-effort timestamp for order and trade rows.

    Unlike the historical endpoints, the book endpoints return times in
    formats that vary by field (`filltime` is `HH:MM:SS` with no date at all).
    Rather than guess a date, an unparseable value becomes `None`: the row's
    *financial* content is required and validated, and a missing display
    timestamp does not justify discarding a real fill.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return parse_exchange_timestamp(value, field)
    except BrokerDataError:
        return None


# -- Market data ------------------------------------------------------------


def map_candles(payload: object, timeframe: Timeframe) -> list[Candle]:
    """Map a `getCandleData` response.

    Rows are positional arrays, `[timestamp, open, high, low, close, volume]`.
    The length is checked before indexing so a changed response shape reports
    as a data error naming the problem, rather than as an `IndexError` from
    somewhere inside a list comprehension.
    """
    rows = _require_list(payload, "getCandleData")
    candles: list[Candle] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            raise BrokerDataError(
                "Angel One returned a candle row that is not a 6-element array."
            )
        candles.append(
            Candle(
                timestamp=parse_exchange_timestamp(row[0], "candle.timestamp"),
                open=parse_decimal(row[1], "candle.open"),
                high=parse_decimal(row[2], "candle.high"),
                low=parse_decimal(row[3], "candle.low"),
                close=parse_decimal(row[4], "candle.close"),
                volume=parse_int(row[5], "candle.volume"),
                timeframe=timeframe,
            )
        )
    return candles


def map_open_interest(payload: object) -> list[OpenInterestObservation]:
    """Map a `getOIData` response.

    Object rows here, not arrays — a different shape from `getCandleData` for
    what is conceptually the same kind of series. That inconsistency is the
    broker's, and containing it is the point of this module.
    """
    rows = _require_list(payload, "getOIData")
    observations: list[OpenInterestObservation] = []
    for row in rows:
        data = require_mapping(row, "getOIData")
        observations.append(
            OpenInterestObservation(
                timestamp=parse_exchange_timestamp(data.get("time"), "oi.time"),
                open_interest=parse_int(data.get("oi"), "oi"),
            )
        )
    return observations


def map_option_greeks(payload: object) -> list[OptionMetrics]:
    """Map an `optionGreek` response.

    Every Greek is optional. The endpoint omits them for contracts it has no
    live data for, and a `0.0` delta is a real value for a deep out-of-the-
    money option — using zero as a stand-in for "missing" would make the two
    indistinguishable at exactly the strikes where the difference matters.
    """
    rows = _require_list(payload, "optionGreek")
    metrics: list[OptionMetrics] = []
    for row in rows:
        data = require_mapping(row, "optionGreek")
        metrics.append(
            OptionMetrics(
                underlying=require_str(data, "name", "optionGreek"),
                expiry=_parse_greek_expiry(data.get("expiry")),
                strike_price=parse_decimal(data.get("strikePrice"), "strikePrice"),
                option_type=_parse_option_type(data.get("optionType")),
                delta=parse_optional_decimal(data.get("delta"), "delta"),
                gamma=parse_optional_decimal(data.get("gamma"), "gamma"),
                theta=parse_optional_decimal(data.get("theta"), "theta"),
                vega=parse_optional_decimal(data.get("vega"), "vega"),
                implied_volatility=parse_optional_decimal(
                    data.get("impliedVolatility"), "impliedVolatility"
                ),
                trade_volume=parse_optional_decimal(
                    data.get("tradeVolume"), "tradeVolume"
                ),
            )
        )
    return metrics


def _parse_greek_expiry(value: object) -> dt.date:
    """Parse `25JAN2024` into a date.

    Parsed with an explicit month table rather than `strptime("%d%b%Y")`,
    because `%b` is locale-sensitive: on a host with a non-English locale the
    same input fails, and the failure would appear only in that deployment.
    """
    if not isinstance(value, str) or not value.strip():
        raise BrokerDataError("Angel One omitted 'expiry' in optionGreek.")
    text = value.strip().upper()
    if len(text) < 8:
        raise BrokerDataError("Angel One sent an unparseable option expiry.")
    try:
        day = int(text[:-7])
        month = _MONTHS[text[-7:-4]]
        year = int(text[-4:])
        return dt.date(year, month, day)
    except (KeyError, ValueError) as exc:
        raise BrokerDataError("Angel One sent an unparseable option expiry.") from exc


_MONTHS: dict[str, int] = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


def _parse_option_type(value: object) -> OptionType:
    """Map `CE`/`PE` to `OptionType`, rejecting anything else.

    An unrecognised right is not defaulted to a call. A Greek attached to the
    wrong side of the chain is worse than no Greek: it has the right magnitude
    and the wrong sign, which is exactly the kind of error that survives a
    sanity check.
    """
    if not isinstance(value, str):
        raise BrokerDataError("Angel One omitted 'optionType' in optionGreek.")
    try:
        return OptionType(value.strip().upper())
    except ValueError as exc:
        raise BrokerDataError(
            f"Angel One sent an unknown option type '{value}'."
        ) from exc
