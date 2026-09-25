"""The binary decoder, tested against hand-packed byte strings.

WHY BYTES AND NOT A MOCK SOCKET
-------------------------------
The thing that can be wrong here is the offset table, and a mock socket cannot
tell you that byte 59 is the average traded price. Only a frame built to the
documented layout and read back can. So every test below constructs bytes,
decodes them, and asserts on the result.

THE FRAMES ARE BUILT BY A HELPER, NOT WRITTEN AS LITERALS
---------------------------------------------------------
A 379-byte literal is unreviewable, and one written by hand would encode the
same misunderstanding as the decoder it is meant to check. `_frame()` packs
fields by keyword at the offsets the *protocol* specifies, which are restated
here rather than imported from `feed_codec` — importing them would make the
test agree with the implementation by construction and prove nothing.

WHAT THESE TESTS CANNOT ESTABLISH
---------------------------------
That the offsets match a live Angel One socket. They are transcribed from the
same published description the decoder uses, so a transcription error is
invisible to both. What is verified is that the decoder is internally
consistent, converts paise exactly, and refuses truncated or unknown frames
instead of returning plausible nonsense. See the `feed_codec` docstring.
"""

from __future__ import annotations

import datetime as dt
import struct
from decimal import Decimal

import pytest
from app.brokers.angel_one.constants import AngelFeedExchangeType, AngelFeedMode
from app.brokers.angel_one.feed_codec import decode_tick
from app.brokers.exceptions import BrokerDataError

# -- Offsets, restated from the protocol description -------------------------
#
# Deliberately not imported from the module under test. A test that shares its
# constants with the code it checks cannot detect a wrong constant.

_MODE = 0
_EXCHANGE = 1
_TOKEN = 2
_SEQUENCE = 27
_TIMESTAMP = 35
_LTP = 43
_LAST_QTY = 51
_AVG_PRICE = 59
_VOLUME = 67
_TOTAL_BUY = 75
_TOTAL_SELL = 83
_OPEN = 91
_HIGH = 99
_LOW = 107
_CLOSE = 115
_OPEN_INTEREST = 131
_DEPTH = 147
_UPPER_CIRCUIT = 347
_LOWER_CIRCUIT = 355
_52W_HIGH = 363
_52W_LOW = 371

_LENGTH = {
    AngelFeedMode.LTP: 51,
    AngelFeedMode.QUOTE: 123,
    AngelFeedMode.SNAP_QUOTE: 379,
}

_DEPTH_RECORD = 20


def _frame(
    mode: AngelFeedMode,
    *,
    exchange: int = int(AngelFeedExchangeType.NSE_FO),
    token: bytes = b"43215",
    timestamp: int = 0,
    ltp: int = 0,
    length: int | None = None,
    **fields: int | float,
) -> bytes:
    """Pack a tick to the documented layout.

    `length` overrides the mode's natural size, which is how the truncation
    tests produce a frame that declares one thing and delivers less.
    """
    buffer = bytearray(_LENGTH[mode] if length is None else length)
    buffer[_MODE] = int(mode)
    buffer[_EXCHANGE] = exchange
    buffer[_TOKEN : _TOKEN + len(token)] = token

    named: dict[str, int | float] = {
        "sequence": fields.pop("sequence", 1),
        "timestamp": timestamp,
        "ltp": ltp,
        **fields,
    }
    offsets: dict[str, int] = {
        "sequence": _SEQUENCE,
        "timestamp": _TIMESTAMP,
        "ltp": _LTP,
        "last_qty": _LAST_QTY,
        "avg_price": _AVG_PRICE,
        "volume": _VOLUME,
        "total_buy": _TOTAL_BUY,
        "total_sell": _TOTAL_SELL,
        "open": _OPEN,
        "high": _HIGH,
        "low": _LOW,
        "close": _CLOSE,
        "open_interest": _OPEN_INTEREST,
        "upper_circuit": _UPPER_CIRCUIT,
        "lower_circuit": _LOWER_CIRCUIT,
        "week52_high": _52W_HIGH,
        "week52_low": _52W_LOW,
    }
    doubles = {"total_buy", "total_sell"}

    for name, value in named.items():
        offset = offsets[name]
        if offset + 8 > len(buffer):
            continue
        if name in doubles:
            struct.pack_into("<d", buffer, offset, float(value))
        else:
            struct.pack_into("<q", buffer, offset, int(value))
    return bytes(buffer)


def _with_depth(
    frame: bytes,
    *,
    bids: list[tuple[int, int, int]],
    asks: list[tuple[int, int, int]],
) -> bytes:
    """Write depth rungs as (quantity, orders, price-in-paise) triples.

    Each 20-byte record is: flag (int16), quantity (int64), orders (int16),
    price (int64). Bids occupy the first five records, asks the next five.
    """
    buffer = bytearray(frame)
    for side_index, rungs in ((0, bids), (5, asks)):
        for index, (quantity, orders, price) in enumerate(rungs):
            base = _DEPTH + (side_index + index) * _DEPTH_RECORD
            struct.pack_into("<h", buffer, base, 1 if side_index == 0 else 0)
            struct.pack_into("<q", buffer, base + 2, quantity)
            struct.pack_into("<h", buffer, base + 10, orders)
            struct.pack_into("<q", buffer, base + 12, price)
    return bytes(buffer)


class TestPaiseConversion:
    def test_price_is_divided_by_exactly_one_hundred(self) -> None:
        """The assertion the module docstring is about.

        2402550 paise is ₹24,025.50. If the divisor were missing the value
        would still be a plausible index level, which is why this is asserted
        rather than eyeballed.
        """
        quote = decode_tick(_frame(AngelFeedMode.LTP, ltp=2402550))
        assert quote.last_traded_price == Decimal("24025.50")

    def test_conversion_is_exact_not_floating_point(self) -> None:
        """A price that has no exact binary representation.

        `12345 / 100` as a float is 123.450000000000002842170943040400743...,
        and `Decimal(that_float)` preserves the error in full. So the second
        assertion is what fails if the divisor is ever applied in binary
        floating point on the way through — note that `Decimal(str(float))`
        would *not* catch it, because `str` rounds to the shortest string that
        round-trips and lands back on "123.45".
        """
        quote = decode_tick(_frame(AngelFeedMode.LTP, ltp=12345))
        assert quote.last_traded_price == Decimal("123.45")
        assert quote.last_traded_price != Decimal(12345 / 100)

    def test_a_price_of_zero_stays_zero(self) -> None:
        """Zero is a real LTP for an instrument that has not traded today.

        It must not become `None`: the two mean different things, and only one
        of them is safe to chart.
        """
        quote = decode_tick(_frame(AngelFeedMode.LTP, ltp=0))
        assert quote.last_traded_price == Decimal("0")


class TestModeBoundaries:
    def test_ltp_mode_leaves_higher_mode_fields_none(self) -> None:
        """An LTP tick has no volume, and says so.

        Reporting zero would be indistinguishable from an instrument nobody
        traded, which is a materially different fact.
        """
        quote = decode_tick(_frame(AngelFeedMode.LTP, ltp=100))
        assert quote.volume_traded is None
        assert quote.open is None
        assert quote.open_interest is None
        assert quote.best_bids == ()

    def test_quote_mode_reads_its_fields_and_stops(self) -> None:
        quote = decode_tick(
            _frame(
                AngelFeedMode.QUOTE,
                ltp=2402550,
                last_qty=75,
                avg_price=2400000,
                volume=185000,
                total_buy=1200.0,
                total_sell=950.0,
                open=2390000,
                high=2410000,
                low=2385000,
                close=2388000,
            )
        )
        assert quote.last_traded_quantity == 75
        assert quote.average_traded_price == Decimal("24000.00")
        assert quote.volume_traded == 185000
        assert quote.open == Decimal("23900.00")
        assert quote.high == Decimal("24100.00")
        assert quote.low == Decimal("23850.00")
        assert quote.close == Decimal("23880.00")
        # Snapshot-only territory stays untouched.
        assert quote.open_interest is None
        assert quote.upper_circuit is None

    def test_snap_quote_reads_the_snapshot_only_fields(self) -> None:
        quote = decode_tick(
            _frame(
                AngelFeedMode.SNAP_QUOTE,
                ltp=2402550,
                open_interest=166100,
                upper_circuit=2640000,
                lower_circuit=2160000,
                week52_high=2650000,
                week52_low=1950000,
            )
        )
        assert quote.open_interest == 166100
        assert quote.upper_circuit == Decimal("26400.00")
        assert quote.lower_circuit == Decimal("21600.00")
        assert quote.fifty_two_week_high == Decimal("26500.00")
        assert quote.fifty_two_week_low == Decimal("19500.00")

    def test_total_quantities_survive_a_fractional_double(self) -> None:
        """The protocol sends these as doubles, so they are carried as Decimal.

        `Decimal(0.1)` is `0.1000000000000000055511151231257827`; going via
        `repr` gives the value that was actually meant.
        """
        quote = decode_tick(
            _frame(AngelFeedMode.QUOTE, total_buy=0.1, total_sell=1200.5)
        )
        assert quote.total_buy_quantity == Decimal("0.1")
        assert quote.total_sell_quantity == Decimal("1200.5")


class TestTruncation:
    def test_a_frame_shorter_than_the_smallest_tick_is_rejected(self) -> None:
        with pytest.raises(BrokerDataError):
            decode_tick(b"\x01\x02" + b"\x00" * 20)

    def test_an_empty_frame_is_rejected(self) -> None:
        with pytest.raises(BrokerDataError):
            decode_tick(b"")

    @pytest.mark.parametrize("mode", [AngelFeedMode.QUOTE, AngelFeedMode.SNAP_QUOTE])
    def test_a_frame_declaring_more_than_it_carries_is_rejected(
        self, mode: AngelFeedMode
    ) -> None:
        """The dangerous case: long enough to decode, too short to be right.

        A QUOTE frame truncated to 51 bytes parses as an LTP tick without
        complaint if the length is not checked against the declared mode — and
        then every field past the cut reads whatever followed in memory.
        """
        truncated = _frame(mode, ltp=100, length=_LENGTH[mode] - 1)
        with pytest.raises(BrokerDataError):
            decode_tick(truncated)

    def test_a_snap_quote_cut_at_the_quote_boundary_is_rejected(self) -> None:
        """Specifically: 123 bytes claiming to be a 379-byte snapshot.

        This one would otherwise succeed all the way through the QUOTE fields
        and only then read past the end.
        """
        frame = _frame(AngelFeedMode.SNAP_QUOTE, ltp=100, length=123)
        with pytest.raises(BrokerDataError):
            decode_tick(frame)


class TestMalformedHeaders:
    def test_an_unknown_mode_is_rejected_not_guessed(self) -> None:
        """Mode 99 is not a mode this build understands.

        Falling back to LTP would report a price read at the right offset from
        a layout that may not have it there.
        """
        frame = bytearray(_frame(AngelFeedMode.LTP, ltp=100))
        frame[_MODE] = 99
        with pytest.raises(BrokerDataError):
            decode_tick(bytes(frame))

    def test_an_unknown_exchange_segment_does_not_discard_the_tick(self) -> None:
        """A segment code we have not been taught about is not a bad price.

        The unmapped value stays visible rather than being coerced to NSE,
        which would attribute the tick to the wrong exchange.
        """
        quote = decode_tick(_frame(AngelFeedMode.LTP, exchange=99, ltp=100))
        assert quote.exchange_segment == "UNKNOWN_99"
        assert quote.last_traded_price == Decimal("1.00")

    def test_a_known_segment_maps_to_its_rest_spelling(self) -> None:
        """So a streamed tick joins to a REST row on exchange_segment."""
        quote = decode_tick(
            _frame(
                AngelFeedMode.LTP,
                exchange=int(AngelFeedExchangeType.NSE_FO),
                ltp=100,
            )
        )
        assert quote.exchange_segment == AngelFeedExchangeType.NSE_FO.name


class TestToken:
    def test_trailing_nuls_are_stripped(self) -> None:
        """A NUL-padded token compares unequal to the REST API's spelling.

        Which would silently break every lookup joining the feed to the
        instrument table — no error, just no matches.
        """
        quote = decode_tick(_frame(AngelFeedMode.LTP, token=b"43215", ltp=100))
        assert quote.token == "43215"

    def test_a_token_filling_the_whole_field_is_read_intact(self) -> None:
        """25 characters with no padding at all, so there is no NUL to find."""
        token = b"A" * 25
        quote = decode_tick(_frame(AngelFeedMode.LTP, token=token, ltp=100))
        assert quote.token == "A" * 25

    def test_undecodable_bytes_do_not_kill_the_tick(self) -> None:
        """Replacement characters beat discarding a readable price."""
        quote = decode_tick(_frame(AngelFeedMode.LTP, token=b"\xff\xfe", ltp=100))
        assert quote.last_traded_price == Decimal("1.00")
        assert quote.token != ""


class TestTimestamps:
    def test_an_epoch_timestamp_becomes_an_aware_utc_datetime(self) -> None:
        """Naive datetimes in a market-data table are a bug waiting to happen."""
        quote = decode_tick(_frame(AngelFeedMode.LTP, timestamp=1790000000, ltp=100))
        assert quote.exchange_timestamp is not None
        assert quote.exchange_timestamp.tzinfo is not None
        assert quote.exchange_timestamp == dt.datetime.fromtimestamp(
            1790000000, tz=dt.UTC
        )

    def test_zero_means_absent_not_nineteen_seventy(self) -> None:
        """Returning the epoch would corrupt any series ordered by time.

        A 1970 timestamp on a live tick sorts before every real observation,
        which is exactly the wrong end.
        """
        quote = decode_tick(_frame(AngelFeedMode.LTP, timestamp=0, ltp=100))
        assert quote.exchange_timestamp is None

    def test_a_negative_timestamp_is_absent_too(self) -> None:
        quote = decode_tick(_frame(AngelFeedMode.LTP, timestamp=-1, ltp=100))
        assert quote.exchange_timestamp is None


class TestDepth:
    def test_both_sides_are_read_in_order(self) -> None:
        frame = _with_depth(
            _frame(AngelFeedMode.SNAP_QUOTE, ltp=2402550),
            bids=[(50, 2, 2402500), (100, 3, 2402450)],
            asks=[(75, 1, 2402600), (25, 4, 2402650)],
        )
        quote = decode_tick(frame)
        assert [level.price for level in quote.best_bids] == [
            Decimal("24025.00"),
            Decimal("24024.50"),
        ]
        assert [level.price for level in quote.best_asks] == [
            Decimal("24026.00"),
            Decimal("24026.50"),
        ]
        assert quote.best_bids[0].quantity == 50
        assert quote.best_bids[0].orders == 2

    def test_empty_rungs_are_padding_not_orders_at_zero_rupees(self) -> None:
        """Five rungs are always sent; a thin book leaves most of them zero.

        Including them would put a ₹0.00 level at the top of the book, which
        any consumer reading `best_bids[0]` would take as the best bid.
        """
        frame = _with_depth(
            _frame(AngelFeedMode.SNAP_QUOTE, ltp=2402550),
            bids=[(50, 2, 2402500)],
            asks=[],
        )
        quote = decode_tick(frame)
        assert len(quote.best_bids) == 1
        assert quote.best_asks == ()

    def test_bids_and_asks_do_not_bleed_into_each_other(self) -> None:
        """The five-record offset between the sides, asserted directly.

        An off-by-one in the base would return the ask ladder as bids — a book
        that looks normal and is inverted.
        """
        frame = _with_depth(
            _frame(AngelFeedMode.SNAP_QUOTE, ltp=2402550),
            bids=[(1, 1, 100)] * 5,
            asks=[(2, 2, 200)] * 5,
        )
        quote = decode_tick(frame)
        assert len(quote.best_bids) == 5
        assert len(quote.best_asks) == 5
        assert {level.quantity for level in quote.best_bids} == {1}
        assert {level.quantity for level in quote.best_asks} == {2}

    def test_a_full_book_yields_exactly_five_levels_per_side(self) -> None:
        """Not six: a sixth would mean the record stride is wrong."""
        frame = _with_depth(
            _frame(AngelFeedMode.SNAP_QUOTE, ltp=2402550),
            bids=[(10 * n, n, 2402500 - 50 * n) for n in range(1, 6)],
            asks=[(10 * n, n, 2402600 + 50 * n) for n in range(1, 6)],
        )
        quote = decode_tick(frame)
        assert len(quote.best_bids) == 5
        assert len(quote.best_asks) == 5
