"""Monthly-target persistence contract."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.domain.models import MonthlyTargetData


@runtime_checkable
class TargetRepository(Protocol):
    """Stores the user's monthly goal.

    Async for the same reason as the other repositories: Phase 3 backs this
    with a row in PostgreSQL. The mock implementation holds it in process
    memory, which is sufficient while there is exactly one user and no
    durability requirement.
    """

    async def get_monthly_target(self) -> MonthlyTargetData: ...

    async def set_monthly_target(self, amount: Decimal) -> MonthlyTargetData: ...
