"""Durable monthly-target store.

This is the class that makes §43 true: a target set before a restart is still
there afterwards, because it lives in a row rather than in process memory.

WHICH MONTH
-----------
The repository protocol takes no year or month — the dashboard only ever edits
"this month's goal". The period is therefore resolved from the exchange-local
date at call time, which is also what makes the row unique: `monthly_targets`
is keyed on `(year, month)`.

HISTORY
-------
Every accepted change appends a `monthly_target_history` row carrying the value
it replaced. That table is append-only, so "why was the daily target ₹500 that
week?" stays answerable after the target moves. The current value lives on
`monthly_targets`; the audit trail is never reconstructed from it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import CURRENCY
from app.db.models.monthly_target import MonthlyTarget, MonthlyTargetHistory
from app.domain.clock import current_period
from app.domain.enums import CalculationMode, TargetChangeSource
from app.domain.models import MonthlyTargetData

#: Goal reported before the user has ever set one. Mirrors the frontend default
#: so a cold start with an empty database reads identically to the mock.
#:
#: Returning this is deliberately a *read*, not a lazy insert: a GET that
#: silently created a row would write to the database on every dashboard load
#: and would fabricate a history entry the user never asked for.
DEFAULT_MONTHLY_TARGET: Final = Decimal("10000.00")


class PostgresTargetRepository:
    """Reads and writes the user's monthly goal."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_monthly_target(self) -> MonthlyTargetData:
        year, month = current_period()
        target = await self._fetch(year, month)
        if target is None:
            return MonthlyTargetData(amount=DEFAULT_MONTHLY_TARGET)
        return MonthlyTargetData(amount=target.target_amount)

    async def set_monthly_target(self, amount: Decimal) -> MonthlyTargetData:
        """Store a pre-validated target and record the change.

        Validation lives in the service layer; a repository's job is storage,
        not policy. The database's `amount_positive` CHECK is the backstop for
        every other writer — seeds, migrations, a future CLI with no Pydantic
        layer in front of it.
        """
        year, month = current_period()
        target = await self._fetch(year, month, for_update=True)

        if target is None:
            target = MonthlyTarget(
                year=year,
                month=month,
                target_amount=amount,
                currency=CURRENCY,
                calculation_mode=CalculationMode.CALENDAR_DAYS_30.value,
            )
            self._session.add(target)
            # The primary key is generated application-side, but the row must
            # reach the database before a history row can reference it.
            await self._session.flush()
            previous: Decimal | None = None
        else:
            # A no-op edit — the dashboard re-submits the same figure whenever
            # the user opens and closes the pencil editor — is not a change,
            # and an audit log full of "₹15,000 became ₹15,000" is noise that
            # makes the real edits harder to find.
            if target.target_amount == amount:
                return MonthlyTargetData(amount=target.target_amount)
            previous = target.target_amount
            target.target_amount = amount

        self._session.add(
            MonthlyTargetHistory(
                monthly_target_id=target.id,
                previous_amount=previous,
                new_amount=amount,
                source=TargetChangeSource.USER.value,
            )
        )
        await self._session.flush()

        return MonthlyTargetData(amount=target.target_amount)

    async def _fetch(
        self, year: int, month: int, *, for_update: bool = False
    ) -> MonthlyTarget | None:
        """Load one month's target row.

        `for_update` takes a row lock for the read-modify-write in
        `set_monthly_target`, so two concurrent edits serialise instead of one
        overwriting the other's history entry. It does nothing when the row
        does not yet exist — there is no row to lock — but the unique
        constraint on `(year, month)` turns that race into a failed insert
        rather than a duplicate target.
        """
        statement = select(MonthlyTarget).where(
            MonthlyTarget.year == year,
            MonthlyTarget.month == month,
        )
        if for_update:
            statement = statement.with_for_update()
        # `scalars().first()` rather than `scalar()`: the latter is typed as
        # returning `Any`, which would erase the model type and silently defeat
        # strict type checking at every call site.
        result = await self._session.scalars(statement)
        return result.first()
