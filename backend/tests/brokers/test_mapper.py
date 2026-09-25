"""The mapper's refusal to invent data.

These are the most important tests in the broker package. Everything else
concerns plumbing; this concerns whether a wrong number can reach the database
looking like a right one.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from app.brokers.angel_one import mapper
from app.brokers.exceptions import BrokerDataError
from app.domain.enums import OptionType, Timeframe

RMS_PAYLOAD = {
    "net": "25000.50",
    "availablecash": "20000.25",
    "availableintradaypayin": "0",
    "availablelimitmargin": "0",
    "collateral": "0",
    "m2munrealized": "-150.75",
    "m2mrealized": "300.00",
    "utiliseddebits": "5000.25",
    "utilisedspan": "4000.00",
    "utilisedoptionpremium": "1000.25",
    "utilisedholdingsales": "0",
    "utilisedexposure": "0",
    "utilisedturnover": "0",
    "utilisedpayout": "0",
}


class TestDecimalParsing:
    def test_parses_a_decimal_string_exactly(self) -> None:
        """The whole reason the pipeline is `Decimal` end to end.

        `0.1 + 0.2` is not `0.3` in binary floating point. If this value went
        through `float` anywhere between the wire and here, the equality below
        fails — which makes this a regression test for the entire numeric
        policy, not just for one function.
        """
        assert mapper.parse_decimal("0.1", "x") + mapper.parse_decimal(
            "0.2", "x"
        ) == Decimal("0.3")

    @pytest.mark.parametrize("missing", [None, "", "   "])
    def test_required_decimal_refuses_to_default(self, missing: object) -> None:
        """A missing required number fails the request rather than becoming 0.

        Angel One uses `""` for "not applicable" on some fields. Reading that
        as zero on a balance is how a dashboard confidently displays ₹0.00 for
        an account holding ₹25,000.
        """
        with pytest.raises(BrokerDataError):
            mapper.parse_decimal(missing, "availablecash")

    def test_unparseable_number_fails(self) -> None:
        with pytest.raises(BrokerDataError):
            mapper.parse_decimal("not-a-number", "ltp")

    def test_optional_decimal_distinguishes_absent_from_malformed(self) -> None:
        """Absent is information; malformed is a broken contract.

        Collapsing the two would hide a real API change behind a `None` that
        looks like a routine omission.
        """
        assert mapper.parse_optional_decimal(None, "collateral") is None
        with pytest.raises(BrokerDataError):
            mapper.parse_optional_decimal("garbage", "collateral")

    def test_integer_accepts_decimal_notation_but_not_fractions(self) -> None:
        """`"100.0"` is a quantity; `"100.5"` is a bug upstream.

        Truncating the second would silently change someone's position size.
        """
        assert mapper.parse_int("100.0", "quantity") == 100
        with pytest.raises(BrokerDataError):
            mapper.parse_int("100.5", "quantity")


class TestFunds:
    def test_maps_every_documented_field(self) -> None:
        funds = mapper.map_funds(
            RMS_PAYLOAD, retrieved_at=dt.datetime(2026, 9, 25, tzinfo=dt.UTC)
        )
        assert funds.net == Decimal("25000.50")
        assert funds.available_cash == Decimal("20000.25")
        assert funds.used_margin == Decimal("5000.25")
        assert funds.unrealized_mtm == Decimal("-150.75")
        assert funds.realized_mtm == Decimal("300.00")

    def test_missing_balance_fails_rather_than_reporting_zero(self) -> None:
        """The single most consequential assertion in this file.

        An account summary that renders ₹0.00 because a field was absent is
        worse than one that renders an error: the user cannot tell, and may act
        on it.
        """
        payload = RMS_PAYLOAD | {"availablecash": ""}
        with pytest.raises(BrokerDataError):
            mapper.map_funds(payload, retrieved_at=dt.datetime.now(tz=dt.UTC))

    def test_absent_optional_component_stays_none(self) -> None:
        payload = {k: v for k, v in RMS_PAYLOAD.items() if k != "utilisedoptionpremium"}
        funds = mapper.map_funds(payload, retrieved_at=dt.datetime.now(tz=dt.UTC))
        assert funds.utilised_option_premium is None


class TestBooks:
    def test_null_book_is_empty_not_an_error(self) -> None:
        """Angel One sends `null`, not `[]`, for an empty book.

        A flat account has no positions, and saying so is a correct answer.
        """
        assert mapper.map_positions(None) == []
        assert mapper.map_order_book(None) == []
        assert mapper.map_trade_book(None) == []

    def test_order_status_is_not_coerced_into_our_enum(self) -> None:
        """The broker's status string survives untranslated.

        Mapping an unrecognised broker status onto the nearest `OrderStatus`
        member would invent a fact about someone's money.
        """
        orders = mapper.map_order_book(
            [
                {
                    "orderid": "24090500001",
                    "tradingsymbol": "NIFTY25SEP2624000CE",
                    "symboltoken": "43215",
                    "exchange": "NFO",
                    "transactiontype": "BUY",
                    "ordertype": "LIMIT",
                    "producttype": "CARRYFORWARD",
                    "status": "open pending",
                    "quantity": "75",
                    "filledshares": "0",
                    "price": "125.50",
                }
            ]
        )
        assert orders[0].status == "open pending"
        assert orders[0].price == Decimal("125.50")

    def test_unparseable_fill_time_does_not_discard_a_real_fill(self) -> None:
        """`filltime` is `HH:MM:SS` with no date, so it will not parse.

        The financial content of the row is required and validated; a missing
        display timestamp is not a reason to throw away a trade that happened.
        """
        trades = mapper.map_trade_book(
            [
                {
                    "fillid": "5001",
                    "orderid": "24090500001",
                    "tradingsymbol": "NIFTY25SEP2624000CE",
                    "symboltoken": "43215",
                    "exchange": "NFO",
                    "transactiontype": "BUY",
                    "producttype": "CARRYFORWARD",
                    "fillsize": "75",
                    "fillprice": "125.50",
                    "filltime": "10:15:32",
                }
            ]
        )
        assert trades[0].price == Decimal("125.50")
        assert trades[0].trade_timestamp is None


class TestCandles:
    def test_maps_positional_rows_and_keeps_the_offset(self) -> None:
        candles = mapper.map_candles(
            [
                [
                    "2026-09-25T09:15:00+05:30",
                    "24000.1",
                    "24050",
                    "23990",
                    "24020",
                    "150",
                ]
            ],
            Timeframe.M5,
        )
        assert candles[0].open == Decimal("24000.1")
        assert candles[0].volume == 150
        assert candles[0].timestamp.utcoffset() == dt.timedelta(hours=5, minutes=30)

    def test_timestamps_are_always_aware(self) -> None:
        """A naive datetime in a market-data table is a bug waiting to happen.

        A value with no offset is read as exchange-local, which is the
        documented behaviour — never as UTC, and never as the host's zone.
        """
        parsed = mapper.parse_exchange_timestamp("2026-09-25T09:15:00", "t")
        assert parsed.utcoffset() == dt.timedelta(hours=5, minutes=30)

    def test_short_row_fails_with_a_data_error_not_an_indexerror(self) -> None:
        with pytest.raises(BrokerDataError):
            mapper.map_candles([["2026-09-25T09:15:00+05:30", "1", "2"]], Timeframe.M5)

    def test_unparseable_price_fails_the_whole_batch(self) -> None:
        """One bad bar invalidates the request rather than being skipped.

        Silently dropping it would leave a gap indistinguishable from a
        genuine trading halt.
        """
        with pytest.raises(BrokerDataError):
            mapper.map_candles(
                [["2026-09-25T09:15:00+05:30", "x", "2", "3", "4", "5"]],
                Timeframe.M5,
            )


class TestOptionGreeks:
    def test_maps_a_chain_row(self) -> None:
        metrics = mapper.map_option_greeks(
            [
                {
                    "name": "NIFTY",
                    "expiry": "25SEP2026",
                    "strikePrice": "24000.000000",
                    "optionType": "CE",
                    "delta": "0.5123",
                    "gamma": "0.0004",
                    "theta": "-8.21",
                    "vega": "12.05",
                    "impliedVolatility": "13.45",
                    "tradeVolume": "185000",
                }
            ]
        )
        assert metrics[0].expiry == dt.date(2026, 9, 25)
        assert metrics[0].option_type is OptionType.CALL
        assert metrics[0].delta == Decimal("0.5123")

    def test_zero_delta_is_preserved_not_treated_as_missing(self) -> None:
        """A 0.0 delta is a real value for a far out-of-the-money option.

        Using zero as a stand-in for "missing" would make the two
        indistinguishable at exactly the strikes where it matters.
        """
        metrics = mapper.map_option_greeks(
            [
                {
                    "name": "NIFTY",
                    "expiry": "25SEP2026",
                    "strikePrice": "30000",
                    "optionType": "CE",
                    "delta": "0",
                }
            ]
        )
        assert metrics[0].delta == Decimal("0")
        assert metrics[0].gamma is None

    def test_unknown_option_type_is_rejected_not_defaulted(self) -> None:
        """A Greek on the wrong side of the chain has the right magnitude and
        the wrong sign — the kind of error that survives a sanity check."""
        with pytest.raises(BrokerDataError):
            mapper.map_option_greeks(
                [
                    {
                        "name": "NIFTY",
                        "expiry": "25SEP2026",
                        "strikePrice": "24000",
                        "optionType": "XX",
                    }
                ]
            )

    def test_expiry_parsing_is_locale_independent(self) -> None:
        """Parsed with an explicit month table rather than `%b`.

        `strptime("%d%b%Y")` fails on a host with a non-English locale, and the
        failure would appear only in that one deployment.
        """
        assert mapper._parse_greek_expiry("01JAN2027") == dt.date(2027, 1, 1)
        assert mapper._parse_greek_expiry("31dec2026") == dt.date(2026, 12, 31)


class TestOpenInterest:
    def test_maps_object_rows(self) -> None:
        observations = mapper.map_open_interest(
            [{"time": "2026-09-25T09:15:00+05:30", "oi": 166100}]
        )
        assert observations[0].open_interest == 166100
