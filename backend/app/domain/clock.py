"""Exchange-local time.

Kept separate from `domain.calculations`, which is deliberately clock-free so
its rules stay exhaustively testable. Everything that needs to know "what day
is it?" goes through here instead, which gives the test suite a single seam to
control rather than a `date.today()` scattered across repositories.

WHY IST AND NOT THE HOST CLOCK
------------------------------
A trading session belongs to a calendar day on the exchange, not to whatever
timezone the server happens to sit in. A process running in UTC would roll over
to the next trading date at 05:30 IST — mid-morning in Mumbai, and squarely
inside a session. Every date this system reasons about is therefore resolved in
`Asia/Kolkata`.
"""

from __future__ import annotations

import datetime as dt

from app.core.constants import IST


def now_ist() -> dt.datetime:
    """The current instant, expressed in exchange-local time."""
    return dt.datetime.now(tz=IST)


def today_ist() -> dt.date:
    """The current trading date on the exchange."""
    return now_ist().date()


def current_period() -> tuple[int, int]:
    """The `(year, month)` the monthly target currently applies to."""
    today = today_ist()
    return today.year, today.month


def month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    """Half-open `[start, end)` date range covering one calendar month.

    Half-open rather than inclusive so callers filter with `>= start AND
    < end`, which is a plain range scan on `trading_date`. The obvious
    alternative — `EXTRACT(YEAR FROM trading_date) = :year` — wraps the column
    in a function call and makes its index unusable.
    """
    start = dt.date(year, month, 1)
    end = dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)
    return start, end
