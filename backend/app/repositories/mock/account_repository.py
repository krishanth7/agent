"""In-memory account repository.

MOCK DATA. These figures are fixed demonstration values. No broker is
connected, and nothing here reflects a real account.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from app.domain.enums import DataSource
from app.domain.models import AccountSummaryData

_SUMMARY: Final = AccountSummaryData(
    available_balance=Decimal("25000.00"),
    used_margin=Decimal("0.00"),
    total_capital=Decimal("25000.00"),
    source=DataSource.MOCK,
)


class MockAccountRepository:
    """Serves a constant funds snapshot.

    Deterministic by design: a repository that jittered its numbers on every
    request would make the dashboard look alive while telling the developer
    nothing, and would make the API untestable.
    """

    async def get_summary(self) -> AccountSummaryData:
        return _SUMMARY
