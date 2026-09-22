"""Account data access contract."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.models import AccountSummaryData


@runtime_checkable
class AccountRepository(Protocol):
    """Source of the trading account's funds snapshot.

    Async because every future implementation performs I/O: Phase 3 reads from
    PostgreSQL, Phase 4 from a broker funds endpoint. Defining the seam now
    means neither swap touches the route or service layer.
    """

    async def get_summary(self) -> AccountSummaryData: ...
