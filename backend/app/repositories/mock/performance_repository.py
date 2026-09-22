"""In-memory trade journal.

MOCK DATA. Every session below is invented for demonstration. No market data
feed, broker or trading engine exists in this phase, and none of these figures
describe real trades.

The dataset mirrors the Phase 1 frontend fixture exactly so the dashboard tells
the same story whether it renders from the bundled mock or from this API. It
covers September 2026 through the 22nd and deliberately includes every state
the calendar can render: target achieved, profit below target, loss, and a
recorded no-trade day (07 Sep). Month-to-date realized P&L is ₹4,280.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Final

from app.domain.models import DailySessionData

#: The dashboard's pinned "today". The mock month is fixed, so the reference
#: date must be too — otherwise the demo would drift out of its own dataset.
#: A real repository returns the current IST date instead.
REFERENCE_DATE: Final = date(2026, 9, 22)


def _session(
    day: int, pnl: str, trades: int, wins: int, losses: int
) -> DailySessionData:
    return DailySessionData(
        session_date=date(2026, 9, day),
        realized_pnl=Decimal(pnl),
        trades=trades,
        wins=wins,
        losses=losses,
    )


_SESSIONS: Final[tuple[DailySessionData, ...]] = (
    _session(1, "410.00", 3, 2, 1),
    _session(2, "185.00", 2, 1, 1),
    _session(3, "-240.00", 3, 1, 2),
    _session(4, "520.00", 4, 3, 1),
    _session(7, "0.00", 0, 0, 0),
    _session(8, "365.00", 2, 2, 0),
    _session(9, "295.00", 3, 2, 1),
    _session(10, "-150.00", 2, 0, 2),
    _session(11, "610.00", 4, 3, 1),
    _session(14, "340.00", 3, 2, 1),
    _session(15, "95.00", 2, 1, 1),
    _session(16, "-310.00", 3, 1, 2),
    _session(17, "455.00", 3, 2, 1),
    _session(18, "825.00", 5, 4, 1),
    _session(21, "460.00", 3, 2, 1),
    _session(22, "420.00", 3, 2, 1),
)

_BY_DATE: Final = {session.session_date: session for session in _SESSIONS}


class MockPerformanceRepository:
    """Serves the fixed September 2026 demo journal."""

    async def get_session(self, session_date: date) -> DailySessionData | None:
        return _BY_DATE.get(session_date)

    async def get_sessions_for_month(
        self, year: int, month: int
    ) -> list[DailySessionData]:
        return [
            session
            for session in _SESSIONS
            if session.session_date.year == year and session.session_date.month == month
        ]

    async def get_reference_date(self) -> date:
        return REFERENCE_DATE
