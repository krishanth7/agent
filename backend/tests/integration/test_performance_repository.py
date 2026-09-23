"""Reading the trade journal out of PostgreSQL.

The month query is the one with teeth. It is written as a half-open range over
`trading_date` so the index is usable; the obvious alternative,
`EXTRACT(YEAR FROM trading_date) = :year`, wraps the column in a function call
and forces a sequential scan. These tests pin the *boundaries* of that range,
because an off-by-one there is silent: the dashboard simply shows a month that
is missing its first or last day, and nobody notices until month end.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.db.models.daily_performance import DailyPerformance
from app.domain.enums import DataSource
from app.repositories.postgres.performance_repository import (
    PostgresPerformanceRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession

_SOURCE = DataSource.DEVELOPMENT_SEED.value


def _row(day: dt.date, pnl: str, trades: int = 2) -> DailyPerformance:
    return DailyPerformance(
        trading_date=day,
        realized_pnl=Decimal(pnl),
        net_pnl=Decimal(pnl),
        fees=Decimal("0"),
        daily_target=Decimal("500"),
        trade_count=trades,
        win_count=trades,
        loss_count=0,
        breakeven_count=0,
        source=_SOURCE,
    )


async def test_missing_day_reads_as_none(db_session: AsyncSession) -> None:
    """A day with no trading is absent, not zero.

    The distinction is real: "I did not trade" and "I traded and broke even"
    are different facts, and collapsing them would corrupt the win-rate
    denominator.
    """
    repository = PostgresPerformanceRepository(db_session)

    assert await repository.get_session(dt.date(2026, 9, 10)) is None


async def test_a_recorded_day_round_trips(db_session: AsyncSession) -> None:
    db_session.add(_row(dt.date(2026, 9, 10), "410.00", trades=3))
    await db_session.flush()

    session = await PostgresPerformanceRepository(db_session).get_session(
        dt.date(2026, 9, 10)
    )

    assert session is not None
    assert session.realized_pnl == Decimal("410.00")
    assert session.trades == 3


async def test_month_query_includes_both_boundaries(db_session: AsyncSession) -> None:
    """The 1st and the last day of the month are inside the range.

    September has 30 days, so a range built as `< 30` rather than `< Oct 1`
    would drop the 30th — the exact off-by-one this asserts against.
    """
    db_session.add_all(
        [
            _row(dt.date(2026, 9, 1), "100.00"),
            _row(dt.date(2026, 9, 30), "200.00"),
        ]
    )
    await db_session.flush()

    sessions = await PostgresPerformanceRepository(db_session).get_sessions_for_month(
        2026, 9
    )

    assert [entry.session_date for entry in sessions] == [
        dt.date(2026, 9, 1),
        dt.date(2026, 9, 30),
    ]


async def test_month_query_excludes_neighbouring_months(
    db_session: AsyncSession,
) -> None:
    """A September query must not see August or October."""
    db_session.add_all(
        [
            _row(dt.date(2026, 8, 31), "999.00"),
            _row(dt.date(2026, 9, 15), "100.00"),
            _row(dt.date(2026, 10, 1), "888.00"),
        ]
    )
    await db_session.flush()

    sessions = await PostgresPerformanceRepository(db_session).get_sessions_for_month(
        2026, 9
    )

    assert [entry.session_date for entry in sessions] == [dt.date(2026, 9, 15)]


async def test_december_rolls_into_the_next_year(db_session: AsyncSession) -> None:
    """Month 12 is where naive `month + 1` arithmetic produces month 13.

    A crash on 31 December is a poor way to discover this.
    """
    db_session.add_all(
        [
            _row(dt.date(2026, 12, 31), "100.00"),
            _row(dt.date(2027, 1, 1), "777.00"),
        ]
    )
    await db_session.flush()

    sessions = await PostgresPerformanceRepository(db_session).get_sessions_for_month(
        2026, 12
    )

    assert [entry.session_date for entry in sessions] == [dt.date(2026, 12, 31)]


async def test_sessions_are_returned_chronologically(db_session: AsyncSession) -> None:
    """Insertion order must not leak into the calendar.

    Rows are added here deliberately out of order; a month-to-date fold over an
    unordered result would still total correctly but would draw the equity
    curve wrong.
    """
    db_session.add_all(
        [
            _row(dt.date(2026, 9, 18), "300.00"),
            _row(dt.date(2026, 9, 2), "100.00"),
            _row(dt.date(2026, 9, 9), "200.00"),
        ]
    )
    await db_session.flush()

    sessions = await PostgresPerformanceRepository(db_session).get_sessions_for_month(
        2026, 9
    )

    assert [entry.session_date for entry in sessions] == [
        dt.date(2026, 9, 2),
        dt.date(2026, 9, 9),
        dt.date(2026, 9, 18),
    ]


async def test_repository_declares_database_provenance(
    db_session: AsyncSession,
) -> None:
    """Part of the repository contract, not an implementation detail.

    The service stamps this into every response, so a repository that forgot it
    would relabel real stored figures as mock.
    """
    assert PostgresPerformanceRepository(db_session).source is DataSource.DATABASE
