"""Splitting a history request into requests the broker will accept.

Angel One caps the calendar span of a single historical request, and the cap
depends on the interval: 30 days at one minute, 2000 at one day. Asking for
more is rejected outright rather than truncated, so a caller wanting a year of
five-minute bars has to issue four requests and stitch them.

Doing that arithmetic at the call site would mean doing it again at the next
call site, slightly differently. It lives here instead, as a pure function over
two datetimes that returns the chunks — which makes the awkward parts (a range
shorter than one chunk, a range that divides exactly, an inverted range) things
a test can assert about without a network.

WHY IT IS NOT A GENERATOR
-------------------------
A list, so the caller can see how many requests it is about to make before
making the first one. "This will be 340 calls against a 3/s limit" is a
decision someone should be able to take, and a lazy sequence hides it until the
loop is already running.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from app.brokers.angel_one.constants import INTERVAL_MAX_DAYS
from app.brokers.exceptions import BrokerDataError
from app.domain.enums import Timeframe


@dataclass(frozen=True, slots=True)
class HistoryChunk:
    """One request-sized slice of a wider range, inclusive at both ends.

    Inclusive because that is how Angel One interprets `fromdate`/`todate`,
    and re-deriving the convention at each call site is how a half-open
    assumption ends up silently dropping the last bar of every chunk.
    """

    start: dt.datetime
    end: dt.datetime


def max_span_days(timeframe: Timeframe) -> int:
    """The broker's per-request cap for an interval.

    Raises rather than falling back to a conservative default. A timeframe
    absent from the table is one this adapter has never been told how to
    request, and quietly using the smallest cap would turn a missing mapping
    into a thousand unnecessary requests that nobody would ever investigate.
    """
    limit = INTERVAL_MAX_DAYS.get(timeframe)
    if limit is None:
        raise BrokerDataError(
            f"No Angel One request limit is known for the '{timeframe.value}' interval."
        )
    return limit


def plan_history_requests(
    timeframe: Timeframe, start: dt.datetime, end: dt.datetime
) -> list[HistoryChunk]:
    """Split `[start, end]` into chunks within the broker's per-request cap.

    Both bounds must be timezone-aware. A naive datetime is rejected rather
    than localised: the only way to localise it correctly is to know which zone
    the caller meant, and guessing IST for a value that was actually UTC shifts
    every returned bar by five and a half hours in a way that still looks like
    plausible market data.

    An inverted range is a caller bug and fails loudly. An instantaneous range
    (`start == end`) is legitimate — it asks for the bar at one moment — and
    yields exactly one chunk.
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise BrokerDataError(
            "Historical range bounds must be timezone-aware datetimes."
        )
    if end < start:
        raise BrokerDataError("Historical range ends before it starts.")

    span = dt.timedelta(days=max_span_days(timeframe))
    chunks: list[HistoryChunk] = []
    cursor = start
    while cursor <= end:
        # Minus one minute so consecutive chunks do not both include the
        # boundary instant. Angel One's bounds are inclusive and its timestamps
        # have minute precision, so without this the last bar of one chunk is
        # also the first bar of the next — a duplicate that an upsert would
        # hide and a plain insert would reject.
        chunk_end = min(cursor + span - dt.timedelta(minutes=1), end)
        chunks.append(HistoryChunk(start=cursor, end=chunk_end))
        if chunk_end >= end:
            break
        cursor = chunk_end + dt.timedelta(minutes=1)

    return chunks
