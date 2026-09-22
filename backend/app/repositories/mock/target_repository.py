"""In-process monthly-target store.

Holds the user's goal for the lifetime of the server process. That is a
deliberate scope choice: introducing a database purely to persist a single
integer would be the wrong trade for this phase. Phase 3 replaces this class
with a PostgreSQL-backed one implementing the same protocol.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Final

from app.domain.models import MonthlyTargetData

#: Starting goal before the user sets their own. Mirrors the Phase 1 frontend
#: default so the dashboard reads identically on a cold start.
DEFAULT_MONTHLY_TARGET: Final = Decimal("10000.00")


class MockTargetRepository:
    """Process-local, concurrency-safe target store."""

    def __init__(self, initial: Decimal = DEFAULT_MONTHLY_TARGET) -> None:
        self._amount = initial
        # Reads and writes are individually atomic in CPython, but the lock
        # documents the intent and keeps the class honest if a future
        # implementation needs a read-modify-write.
        self._lock = asyncio.Lock()

    async def get_monthly_target(self) -> MonthlyTargetData:
        async with self._lock:
            return MonthlyTargetData(amount=self._amount)

    async def set_monthly_target(self, amount: Decimal) -> MonthlyTargetData:
        """Store a pre-validated target.

        Validation lives in the service layer; a repository's job is storage,
        not policy. Passing an invalid amount here is a programming error.
        """
        async with self._lock:
            self._amount = amount
            return MonthlyTargetData(amount=self._amount)
