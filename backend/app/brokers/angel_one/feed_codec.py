"""Decoding SmartWebSocketV2 binary frames.

The feed does not send JSON. Each tick is a packed little-endian binary
structure whose length depends on the subscription mode, and every field is
read by byte offset.

WHY THIS IS A SEPARATE MODULE WITH NO I/O
-----------------------------------------
Decoding is pure: bytes in, a `BrokerQuote` out. Keeping it away from the
socket means the offset table — the part that is easy to get wrong and
impossible to eyeball — can be tested against fixed byte strings, exhaustively,
in microseconds. A decoder that can only be exercised through a live
WebSocket is a decoder that is not exercised.

THE PAISE PROBLEM
-----------------
Every price on this feed is an integer in paise. 2402550 is ₹24,025.50.

Forgetting the conversion does not produce an obvious failure: it produces a
number that is exactly 100x too large, which still looks like a price, still
serializes, still renders, and on an index quoted in tens of thousands is not
visibly absurd. Getting it wrong in the other direction is worse still. So the
divisor is applied in exactly one function, as `Decimal`, and is asserted on in
the tests.

OFFSETS ARE UNVERIFIED AGAINST A LIVE FEED
------------------------------------------
The layout below is transcribed from the published protocol description. It has
not been checked against bytes from a real socket, because doing so requires a
funded account and a live session. It is marked as such here, and on the
`subscribe` path, so that nobody builds on it believing it is confirmed.
"""

from __future__ import annotations

import datetime as dt
import struct
from dataclasses import replace
from decimal import Decimal
from typing import Final

from app.brokers.angel_one.constants import (
    FEED_PRICE_DIVISOR,
    AngelFeedExchangeType,
    AngelFeedMode,
)
from app.brokers.exceptions import BrokerDataError
from app.brokers.models import BrokerQuote, DepthLevel

#: `Decimal`, not `int`, so `price / _DIVISOR` stays exact. Dividing a Decimal
#: by an int works, but fixing the type here makes the intent unmissable.
_DIVISOR: Final = Decimal(FEED_PRICE_DIVISOR)

# -- Field offsets ----------------------------------------------------------
#
# Byte positions within a tick, from the start of the frame. Named rather than
# inlined: `data[43:51]` at a call site is unreviewable, and an off-by-one in
# it produces a plausible number rather than an error.

_OFF_MODE: Final = 0
_OFF_EXCHANGE_TYPE: Final = 1
_OFF_TOKEN: Final = 2
_OFF_TOKEN_END: Final = 27
_OFF_SEQUENCE: Final = 27
_OFF_EXCHANGE_TIMESTAMP: Final = 35
_OFF_LTP: Final = 43

#: Present from QUOTE mode upward.
_OFF_LAST_TRADED_QTY: Final = 51
_OFF_AVG_TRADED_PRICE: Final = 59
_OFF_VOLUME: Final = 67
_OFF_TOTAL_BUY_QTY: Final = 75
_OFF_TOTAL_SELL_QTY: Final = 83
_OFF_OPEN: Final = 91
_OFF_HIGH: Final = 99
_OFF_LOW: Final = 107
_OFF_CLOSE: Final = 115

#: Present only in SNAP_QUOTE.
_OFF_LAST_TRADED_TIMESTAMP: Final = 123
_OFF_OPEN_INTEREST: Final = 131
_OFF_UPPER_CIRCUIT: Final = 347
_OFF_LOWER_CIRCUIT: Final = 355
_OFF_52W_HIGH: Final = 363
_OFF_52W_LOW: Final = 371

#: Five bid rungs then five ask rungs, each a 20-byte record.
_OFF_DEPTH: Final = 147
_DEPTH_RECORD_SIZE: Final = 20
_DEPTH_LEVELS: Final = 5

#: Minimum frame length per mode. A frame shorter than this is truncated, and
#: reading past it would either raise deep inside `struct` or — worse — succeed
#: against whatever bytes happened to follow.
_MIN_LENGTH: Final[dict[AngelFeedMode, int]] = {
    AngelFeedMode.LTP: 51,
    AngelFeedMode.QUOTE: 123,
    AngelFeedMode.SNAP_QUOTE: 379,
}


def _int64(data: bytes, offset: int) -> int:
    """Little-endian signed 64-bit read, with a bounds check that explains."""
    if offset + 8 > len(data):
        raise BrokerDataError(
            f"Feed frame is too short to read the field at byte {offset}."
        )
    return int(struct.unpack_from("<q", data, offset)[0])


def _int16(data: bytes, offset: int) -> int:
    if offset + 2 > len(data):
        raise BrokerDataError(
            f"Feed frame is too short to read the field at byte {offset}."
        )
    return int(struct.unpack_from("<h", data, offset)[0])


def _price(data: bytes, offset: int) -> Decimal:
    """Read a paise integer and return rupees.

    The only place the conversion happens. See the module docstring.
    """
    return Decimal(_int64(data, offset)) / _DIVISOR


def _timestamp(data: bytes, offset: int) -> dt.datetime | None:
    """Read an epoch-seconds field as an aware UTC datetime.

    Zero means "not set" on this feed rather than 1 January 1970, so it becomes
    `None`. Returning the epoch would put a 1970 timestamp on a live tick and
    quietly corrupt any series ordered by time.
    """
    seconds = _int64(data, offset)
    if seconds <= 0:
        return None
    return dt.datetime.fromtimestamp(seconds, tz=dt.UTC)


def _token(data: bytes) -> str:
    """Read the null-padded 25-byte token field.

    Trailing NULs are stripped rather than kept. A token carrying them compares
    unequal to the same token from the REST API, which would silently break
    every lookup that joins the two sources.
    """
    raw = data[_OFF_TOKEN:_OFF_TOKEN_END]
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()


def _exchange_segment(data: bytes) -> str:
    """Map the numeric segment code back to its REST spelling.

    An unknown code is rendered as `UNKNOWN_<n>` rather than raising. A segment
    this build has not been taught about is not a reason to discard a tick
    whose price is perfectly readable — and the unmapped value stays visible
    rather than being silently coerced to NSE.
    """
    code = data[_OFF_EXCHANGE_TYPE]
    try:
        return AngelFeedExchangeType(code).name
    except ValueError:
        return f"UNKNOWN_{code}"


def _depth(data: bytes, *, buy: bool) -> tuple[DepthLevel, ...]:
    """Read one side of the five-level order book.

    Each 20-byte record is: buy/sell flag (int16), quantity (int64), orders
    (int16), price (int64). Buy rungs occupy the first five records and sell
    rungs the next five.
    """
    levels: list[DepthLevel] = []
    base = _OFF_DEPTH + (0 if buy else _DEPTH_LEVELS * _DEPTH_RECORD_SIZE)
    for index in range(_DEPTH_LEVELS):
        offset = base + index * _DEPTH_RECORD_SIZE
        quantity = _int64(data, offset + 2)
        orders = _int16(data, offset + 10)
        price = Decimal(_int64(data, offset + 12)) / _DIVISOR
        # An empty rung is padding, not a resting order at ₹0.00. Including it
        # would put a zero-priced level at the top of the book.
        if quantity == 0 and price == 0:
            continue
        levels.append(DepthLevel(price=price, quantity=quantity, orders=orders))
    return tuple(levels)


def decode_tick(frame: bytes) -> BrokerQuote:
    """Decode one binary tick into a `BrokerQuote`.

    Fields absent from the frame's mode stay `None` rather than becoming zero.
    An LTP tick genuinely does not carry a volume, and reporting one of zero
    would be indistinguishable from an instrument that had not traded.
    """
    if len(frame) < _MIN_LENGTH[AngelFeedMode.LTP]:
        raise BrokerDataError(
            f"Feed frame is {len(frame)} bytes; the shortest valid tick is "
            f"{_MIN_LENGTH[AngelFeedMode.LTP]}."
        )

    try:
        mode = AngelFeedMode(frame[_OFF_MODE])
    except ValueError as exc:
        raise BrokerDataError(
            f"Feed frame declares unknown subscription mode {frame[_OFF_MODE]}."
        ) from exc

    minimum = _MIN_LENGTH.get(mode)
    if minimum is not None and len(frame) < minimum:
        # Truncated rather than short-by-mode: reading on would produce values
        # from whatever bytes follow, which decode into plausible prices.
        raise BrokerDataError(
            f"Feed frame declares {mode.name} but is only {len(frame)} bytes."
        )

    quote = BrokerQuote(
        token=_token(frame),
        exchange_segment=_exchange_segment(frame),
        last_traded_price=_price(frame, _OFF_LTP),
        exchange_timestamp=_timestamp(frame, _OFF_EXCHANGE_TIMESTAMP),
    )
    if mode is AngelFeedMode.LTP:
        return quote

    quote = _with_quote_fields(quote, frame)
    if mode is AngelFeedMode.QUOTE:
        return quote

    return _with_snapshot_fields(quote, frame)


def _with_quote_fields(quote: BrokerQuote, frame: bytes) -> BrokerQuote:
    """Add the fields QUOTE mode carries beyond LTP.

    `dataclasses.replace` rather than mutation — `BrokerQuote` is frozen, and
    building it up in layers mirrors how the modes nest.
    """
    return replace(
        quote,
        last_traded_quantity=_int64(frame, _OFF_LAST_TRADED_QTY),
        average_traded_price=_price(frame, _OFF_AVG_TRADED_PRICE),
        volume_traded=_int64(frame, _OFF_VOLUME),
        # Totals are quantities, but the protocol sends them as doubles rather
        # than integers, so they are carried as `Decimal` rather than silently
        # truncated to `int`.
        total_buy_quantity=_decimal_double(frame, _OFF_TOTAL_BUY_QTY),
        total_sell_quantity=_decimal_double(frame, _OFF_TOTAL_SELL_QTY),
        open=_price(frame, _OFF_OPEN),
        high=_price(frame, _OFF_HIGH),
        low=_price(frame, _OFF_LOW),
        close=_price(frame, _OFF_CLOSE),
    )


def _with_snapshot_fields(quote: BrokerQuote, frame: bytes) -> BrokerQuote:
    """Add the fields only SNAP_QUOTE carries."""
    return replace(
        quote,
        open_interest=_int64(frame, _OFF_OPEN_INTEREST),
        upper_circuit=_price(frame, _OFF_UPPER_CIRCUIT),
        lower_circuit=_price(frame, _OFF_LOWER_CIRCUIT),
        fifty_two_week_high=_price(frame, _OFF_52W_HIGH),
        fifty_two_week_low=_price(frame, _OFF_52W_LOW),
        best_bids=_depth(frame, buy=True),
        best_asks=_depth(frame, buy=False),
    )


def _decimal_double(data: bytes, offset: int) -> Decimal:
    """Read an IEEE-754 double and convert via `str`.

    `Decimal(float)` captures the binary approximation — `Decimal(0.1)` is
    `0.1000000000000000055511151231257827`. Going through `repr` gives the
    shortest string that round-trips, which is the value that was meant.
    """
    if offset + 8 > len(data):
        raise BrokerDataError(
            f"Feed frame is too short to read the field at byte {offset}."
        )
    value = float(struct.unpack_from("<d", data, offset)[0])
    return Decimal(repr(value))
