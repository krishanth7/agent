"""Trade-journal data access contract."""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from app.domain.models import DailySessionData


@runtime_checkable
class PerformanceRepository(Protocol):
    """Source of realized session outcomes.

    Phase 3 replaces the mock with a query against the trade journal; the
    method shapes below are already the ones a SQL implementation wants
    (one row, one month, and the anchor date), so no route changes.
    """

    async def get_session(self, session_date: date) -> DailySessionData | None:
        """Return one session, or `None` when nothing was recorded."""
        ...

    async def get_sessions_for_month(
        self, year: int, month: int
    ) -> list[DailySessionData]:
        """Return the month's sessions in chronological order."""
        ...

    async def get_reference_date(self) -> date:
        """The date the dashboard should treat as "today".

        Exists because the demo dataset is pinned to September 2026 so the
        mock story stays coherent. A real implementation returns the current
        IST date and this seam disappears.
        """
        ...
