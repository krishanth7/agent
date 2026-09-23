"""Trade journal, read from `daily_performance`.

WHAT IS RETURNED, AND WHAT IS NOT
---------------------------------
The repository returns stored facts only — realized P&L and the trade counts.
Win rate, progress, remaining-to-target and the achieved/loss status are all
derived by `domain.calculations` from those facts plus the prevailing target.
That split is why editing a monthly target instantly changes every status on
the dashboard instead of leaving stale values behind in the database.

REALIZED, NOT NET
-----------------
`DailySessionData.realized_pnl` maps to the `realized_pnl` column, not
`net_pnl`. The two differ by fees, and the dashboard's P&L figure has meant
gross realized since Phase 1. Silently switching it to net here would change
every number on screen with no visible cause. Surfacing fees is a deliberate
product decision for a later phase, and it needs its own field rather than a
quiet redefinition of this one.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.daily_performance import DailyPerformance
from app.domain.clock import month_bounds, today_ist
from app.domain.enums import DataSource
from app.domain.models import DailySessionData


class PostgresPerformanceRepository:
    """Serves recorded trading sessions."""

    #: Responses built from these rows report `database`, not `mock`.
    #:
    #: Note what this claims and what it does not: it says the figures were
    #: read from this system's own store, not that they came from an exchange.
    #: Rows written by `python -m app.db.seed` carry `development_seed` in
    #: their own `source` column, so invented data stays traceable at the row
    #: level even though the response envelope says `database`.
    source = DataSource.DATABASE

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_session(self, session_date: dt.date) -> DailySessionData | None:
        # `scalars().first()` rather than `scalar()`: the latter is typed as
        # returning `Any`, which would erase the model type at the call site.
        result = await self._session.scalars(
            select(DailyPerformance).where(
                DailyPerformance.trading_date == session_date
            )
        )
        row = result.first()
        return None if row is None else _to_domain(row)

    async def get_sessions_for_month(
        self, year: int, month: int
    ) -> list[DailySessionData]:
        start, end = month_bounds(year, month)
        rows = await self._session.scalars(
            select(DailyPerformance)
            .where(
                DailyPerformance.trading_date >= start,
                DailyPerformance.trading_date < end,
            )
            # Chronological, so the calendar and the month-to-date fold both
            # see days in the order they happened.
            .order_by(DailyPerformance.trading_date)
        )
        return [_to_domain(row) for row in rows]

    async def get_reference_date(self) -> dt.date:
        """The date the dashboard treats as "today".

        The mock pinned this to a fixed day so its invented September 2026
        story stayed coherent. Backed by a real table there is nothing to pin
        to: the answer is simply the current exchange-local date, and a month
        with no recorded sessions correctly renders as an empty calendar.
        """
        return today_ist()


def _to_domain(row: DailyPerformance) -> DailySessionData:
    return DailySessionData(
        session_date=row.trading_date,
        realized_pnl=row.realized_pnl,
        trades=row.trade_count,
        wins=row.win_count,
        losses=row.loss_count,
    )
