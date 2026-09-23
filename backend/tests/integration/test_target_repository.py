"""The monthly target, against a real database.

§43 is the requirement this file exists to make true: the monthly target must
survive a restart. The restart itself is proven in `test_persistence.py`; here
the concern is that the repository writes what it claims to, reads back exactly
what it wrote, and records the change history that makes an edit auditable.
"""

from __future__ import annotations

from decimal import Decimal

from app.db.models.monthly_target import MonthlyTarget, MonthlyTargetHistory
from app.domain.clock import current_period
from app.repositories.postgres.target_repository import (
    DEFAULT_MONTHLY_TARGET,
    PostgresTargetRepository,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def test_absent_target_reads_as_the_default(db_session: AsyncSession) -> None:
    """An empty database must answer, not fail.

    A fresh install has no row for this month. Returning the documented default
    is what lets the dashboard render on first run; raising "not found" would
    make an empty database look like a broken one.
    """
    repository = PostgresTargetRepository(db_session)

    target = await repository.get_monthly_target()

    assert target.amount == DEFAULT_MONTHLY_TARGET


async def test_target_round_trips_exactly(db_session: AsyncSession) -> None:
    """Written and read back with no precision lost.

    Asserted with `Decimal` rather than `float` on purpose. `15000.50` has no
    exact binary representation, so a column or a conversion that quietly went
    through `float` would pass a float comparison and still be wrong — which is
    the class of bug that makes money figures drift.
    """
    repository = PostgresTargetRepository(db_session)

    await repository.set_monthly_target(Decimal("15000.50"))
    await db_session.commit()
    db_session.expunge_all()

    assert (await repository.get_monthly_target()).amount == Decimal("15000.50")


async def test_second_write_updates_rather_than_duplicates(
    db_session: AsyncSession,
) -> None:
    """One target per month, enforced by the read-modify-write path.

    Two rows for the same month would make "the monthly target" ambiguous, and
    which one the dashboard showed would depend on row order.
    """
    repository = PostgresTargetRepository(db_session)
    year, month = current_period()

    await repository.set_monthly_target(Decimal("15000.00"))
    await repository.set_monthly_target(Decimal("22500.00"))
    await db_session.commit()

    rows = (
        await db_session.scalars(
            select(MonthlyTarget).where(
                MonthlyTarget.year == year, MonthlyTarget.month == month
            )
        )
    ).all()

    assert len(rows) == 1
    assert rows[0].target_amount == Decimal("22500.00")


async def test_every_change_is_recorded(db_session: AsyncSession) -> None:
    """The audit trail is the point: a target change must be explicable later.

    The first entry has no previous amount — there was nothing before it — and
    each subsequent entry chains from the last.
    """
    repository = PostgresTargetRepository(db_session)

    await repository.set_monthly_target(Decimal("15000.00"))
    await repository.set_monthly_target(Decimal("22500.00"))
    await db_session.commit()

    history = (await db_session.scalars(select(MonthlyTargetHistory))).all()

    # Compared as a set, not a sequence. `changed_at` defaults to the
    # transaction timestamp, so two entries written in one transaction carry
    # the *same* instant and cannot be ordered by it — an order-dependent
    # assertion here would pass or fail on row layout.
    assert {(entry.previous_amount, entry.new_amount) for entry in history} == {
        (None, Decimal("15000.00")),
        (Decimal("15000.00"), Decimal("22500.00")),
    }


async def test_a_no_op_edit_writes_no_history(db_session: AsyncSession) -> None:
    """Saving the same number twice is not a change.

    Without this, a dashboard that PUTs the target on every render would fill
    the audit log with "₹15,000 became ₹15,000" — and a log that is mostly
    noise is one nobody reads when it matters.
    """
    repository = PostgresTargetRepository(db_session)

    await repository.set_monthly_target(Decimal("15000.00"))
    await repository.set_monthly_target(Decimal("15000.00"))
    await db_session.commit()

    history = (await db_session.scalars(select(MonthlyTargetHistory))).all()

    assert len(history) == 1
