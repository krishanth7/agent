"""The historical range planner.

Pure arithmetic over two datetimes, which is why it is tested exhaustively
here rather than through the adapter: the awkward cases (a range shorter than
one chunk, a range that divides exactly, an inverted range) are cheap to assert
directly and expensive to provoke over a mocked transport.
"""

from __future__ import annotations

import datetime as dt
from itertools import pairwise

import pytest
from app.brokers.angel_one.history import max_span_days, plan_history_requests
from app.brokers.exceptions import BrokerDataError
from app.core.constants import IST
from app.domain.enums import Timeframe


def ist(
    year: int, month: int, day: int, hour: int = 9, minute: int = 15
) -> dt.datetime:
    return dt.datetime(year, month, day, hour, minute, tzinfo=IST)


class TestPlanning:
    def test_a_short_range_is_one_request(self) -> None:
        chunks = plan_history_requests(Timeframe.M5, ist(2026, 9, 1), ist(2026, 9, 10))
        assert len(chunks) == 1
        assert chunks[0].start == ist(2026, 9, 1)
        assert chunks[0].end == ist(2026, 9, 10)

    def test_a_wide_range_is_split_to_the_brokers_cap(self) -> None:
        """One-minute bars are capped at 30 days per request.

        A year is therefore thirteen requests, not one rejected one.
        """
        chunks = plan_history_requests(Timeframe.M1, ist(2026, 1, 1), ist(2026, 12, 31))
        assert len(chunks) == 13
        for chunk in chunks:
            span = chunk.end - chunk.start
            assert span <= dt.timedelta(days=max_span_days(Timeframe.M1))

    def test_chunks_are_contiguous_and_never_overlap(self) -> None:
        """The boundary case that a plain insert would reject and an upsert
        would hide: the last bar of one chunk also being the first of the next.

        Angel One's bounds are inclusive, so consecutive chunks must be exactly
        one minute apart — not zero, which duplicates, and not two, which drops
        a bar.
        """
        chunks = plan_history_requests(Timeframe.M5, ist(2026, 1, 1), ist(2026, 12, 31))
        assert len(chunks) > 1
        for earlier, later in pairwise(chunks):
            assert later.start - earlier.end == dt.timedelta(minutes=1)

    def test_the_plan_covers_the_whole_requested_range(self) -> None:
        start, end = ist(2026, 2, 3), ist(2026, 11, 20, 15, 30)
        chunks = plan_history_requests(Timeframe.M3, start, end)
        assert chunks[0].start == start
        assert chunks[-1].end == end

    def test_an_instantaneous_range_yields_one_chunk(self) -> None:
        """`start == end` asks for the bar at one moment. Legitimate."""
        moment = ist(2026, 9, 25)
        chunks = plan_history_requests(Timeframe.M1, moment, moment)
        assert len(chunks) == 1
        assert chunks[0].start == chunks[0].end == moment

    def test_an_inverted_range_fails_loudly(self) -> None:
        with pytest.raises(BrokerDataError):
            plan_history_requests(Timeframe.M1, ist(2026, 9, 25), ist(2026, 9, 1))

    def test_naive_bounds_are_rejected_rather_than_assumed(self) -> None:
        """Guessing IST for a value that was actually UTC shifts every bar by
        five and a half hours and still returns plausible market data."""
        naive = dt.datetime(2026, 9, 1, 9, 15)
        with pytest.raises(BrokerDataError):
            plan_history_requests(Timeframe.M1, naive, ist(2026, 9, 10))


class TestCaps:
    @pytest.mark.parametrize(
        ("timeframe", "expected"),
        [
            (Timeframe.M1, 30),
            (Timeframe.M3, 60),
            (Timeframe.M5, 100),
            (Timeframe.M15, 200),
            (Timeframe.M30, 200),
            (Timeframe.H1, 400),
            (Timeframe.D1, 2000),
        ],
    )
    def test_published_caps(self, timeframe: Timeframe, expected: int) -> None:
        """Pinned to the broker's published figures.

        If Angel One changes a cap, this test is where that shows up — rather
        than as an intermittently rejected request in production.
        """
        assert max_span_days(timeframe) == expected

    def test_every_timeframe_the_adapter_can_request_has_a_cap(self) -> None:
        """Guards the one way these two tables can drift apart.

        `TIMEFRAME_TO_INTERVAL` says which intervals the adapter will ask for;
        `INTERVAL_MAX_DAYS` says how much it may ask for at once. An interval
        present in the first and missing from the second is a request that
        builds fine and is rejected by the broker.
        """
        from app.brokers.angel_one.constants import (
            INTERVAL_MAX_DAYS,
            TIMEFRAME_TO_INTERVAL,
        )

        assert set(TIMEFRAME_TO_INTERVAL) == set(INTERVAL_MAX_DAYS)
