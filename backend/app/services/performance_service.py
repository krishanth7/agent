"""Performance application service.

All derived figures — status, remaining, progress, win rate — are produced here
by delegating to `domain.calculations`. Routes never compute anything, and no
percentage is ever hard-coded.

MISSING-DATA POLICY
-------------------
The two read paths answer "no record" differently, on purpose:

* ``GET /performance/{date}`` returns **404**. Asking for a specific historical
  session that was never recorded is a miss, and the caller should know.
* ``GET /performance/today`` returns a **zero-filled record**. The dashboard
  must always be able to render today's card, and a trading day that has not
  traded yet is genuinely ``not_started`` rather than absent.
* The calendar simply **omits** dates with no record, so the UI can distinguish
  "no session recorded" from "traded to flat" — different facts that must not
  collapse into the same cell.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.exceptions import PerformanceRecordNotFoundError
from app.domain.calculations import (
    calculate_daily_target,
    calculate_progress_percentage,
    calculate_remaining_to_target,
    calculate_win_rate,
    get_daily_target_status,
    quantize_money,
)
from app.domain.models import DailySessionData, PerformanceTotals
from app.repositories.interfaces.performance_repository import PerformanceRepository
from app.repositories.interfaces.target_repository import TargetRepository
from app.schemas.performance import (
    CalendarDayResponse,
    DailyPerformanceResponse,
    MonthlyPerformanceResponse,
    PerformanceCalendarResponse,
)


class PerformanceService:
    """Reads the trade journal and derives everything the dashboard shows."""

    def __init__(
        self,
        performance_repository: PerformanceRepository,
        target_repository: TargetRepository,
    ) -> None:
        self._performance = performance_repository
        self._targets = target_repository

    async def get_reference_date(self) -> date:
        return await self._performance.get_reference_date()

    async def get_today(self) -> DailyPerformanceResponse:
        today = await self._performance.get_reference_date()
        session = await self._performance.get_session(today)
        if session is None:
            session = _empty_session(today)
        return self._to_daily_response(session, await self._daily_target())

    async def get_for_date(self, session_date: date) -> DailyPerformanceResponse:
        session = await self._performance.get_session(session_date)
        if session is None:
            raise PerformanceRecordNotFoundError(
                f"No performance record exists for {session_date.isoformat()}."
            )
        return self._to_daily_response(session, await self._daily_target())

    async def get_monthly(
        self, year: int | None = None, month: int | None = None
    ) -> MonthlyPerformanceResponse:
        reference = await self._performance.get_reference_date()
        resolved_year = year if year is not None else reference.year
        resolved_month = month if month is not None else reference.month

        sessions = await self._performance.get_sessions_for_month(
            resolved_year, resolved_month
        )
        totals = _aggregate(sessions)

        monthly_target = (await self._targets.get_monthly_target()).amount

        return MonthlyPerformanceResponse(
            year=resolved_year,
            month=resolved_month,
            realized_pnl=quantize_money(totals.realized_pnl),
            monthly_target=quantize_money(monthly_target),
            remaining_to_target=calculate_remaining_to_target(
                totals.realized_pnl, monthly_target
            ),
            progress_percentage=calculate_progress_percentage(
                totals.realized_pnl, monthly_target
            ),
            trades=totals.trades,
            wins=totals.wins,
            losses=totals.losses,
            active_sessions=totals.active_sessions,
        )

    async def get_calendar(self, year: int, month: int) -> PerformanceCalendarResponse:
        sessions = await self._performance.get_sessions_for_month(year, month)
        daily_target = await self._daily_target()

        return PerformanceCalendarResponse(
            year=year,
            month=month,
            days=[
                CalendarDayResponse(
                    date=session.session_date,
                    realized_pnl=quantize_money(session.realized_pnl),
                    trades=session.trades,
                    wins=session.wins,
                    losses=session.losses,
                    daily_target=daily_target,
                    status=get_daily_target_status(
                        session.realized_pnl, Decimal(daily_target)
                    ),
                )
                for session in sessions
            ],
        )

    async def _daily_target(self) -> int:
        target = await self._targets.get_monthly_target()
        return calculate_daily_target(target.amount)

    @staticmethod
    def _to_daily_response(
        session: DailySessionData, daily_target: int
    ) -> DailyPerformanceResponse:
        target = Decimal(daily_target)
        return DailyPerformanceResponse(
            date=session.session_date,
            realized_pnl=quantize_money(session.realized_pnl),
            daily_target=daily_target,
            remaining_to_target=calculate_remaining_to_target(
                session.realized_pnl, target
            ),
            progress_percentage=calculate_progress_percentage(
                session.realized_pnl, target
            ),
            status=get_daily_target_status(session.realized_pnl, target),
            trades=session.trades,
            wins=session.wins,
            losses=session.losses,
            win_rate=calculate_win_rate(session.wins, session.trades),
        )


def _empty_session(session_date: date) -> DailySessionData:
    return DailySessionData(
        session_date=session_date,
        realized_pnl=Decimal("0.00"),
        trades=0,
        wins=0,
        losses=0,
    )


def _aggregate(sessions: list[DailySessionData]) -> PerformanceTotals:
    """Fold sessions into month-to-date totals.

    `active_sessions` counts only days that actually traded, so a recorded
    no-trade day does not drag down an average-per-session figure.
    """
    realized = Decimal("0.00")
    trades = wins = losses = active = 0

    for session in sessions:
        realized += session.realized_pnl
        trades += session.trades
        wins += session.wins
        losses += session.losses
        if session.trades > 0:
            active += 1

    return PerformanceTotals(
        realized_pnl=realized,
        trades=trades,
        wins=wins,
        losses=losses,
        active_sessions=active,
    )
