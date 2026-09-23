"""The development seed, against a real database.

§45 requires the seed to be deterministic, repeatable and idempotent, and §46
requires every row it writes to be traceable as invented. Those are not
cosmetic properties. A seed that writes different numbers on each run makes
every other test flaky; a seed that duplicates on re-run makes `make reset`
destructive; and a seed whose rows are indistinguishable from real ones is how
a fabricated ₹15,000 target eventually gets quoted as a fact.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.db.models.daily_performance import DailyPerformance
from app.db.models.instrument import MarketInstrument
from app.db.models.market_data import IndiaVix, OhlcvCandle
from app.db.models.monthly_target import MonthlyTarget, MonthlyTargetHistory
from app.db.seed import (
    SEED_MONTHLY_TARGET,
    SEED_SOURCE,
    elapsed_trading_days,
    seed_database,
)
from app.db.session import session_scope
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

#: A fixed period, so these assertions do not change meaning on the first of
#: the month. The seed takes the period as an argument precisely so it can be
#: exercised without waiting for the calendar.
_YEAR = 2026
_MONTH = 9
_THROUGH = dt.date(2026, 9, 23)


async def _snapshot(session: AsyncSession) -> dict[str, object]:
    """Everything a re-run must not change.

    Business columns only. `created_at` and `ingested_at` are server-clock
    defaults, so including them would make an honest re-run look like a
    determinism failure for a reason that has nothing to do with the seed.
    """
    return {
        "sessions": [
            (row.trading_date, row.realized_pnl, row.trade_count, row.source)
            for row in (
                await session.scalars(
                    select(DailyPerformance).order_by(DailyPerformance.trading_date)
                )
            ).all()
        ],
        "candles": [
            (
                row.timestamp,
                row.instrument_id,
                row.timeframe,
                row.open,
                row.high,
                row.low,
                row.close,
                row.volume,
                row.source,
            )
            for row in (
                await session.scalars(
                    select(OhlcvCandle).order_by(OhlcvCandle.timestamp)
                )
            ).all()
        ],
        "vix": [
            (row.timestamp, row.open, row.high, row.low, row.close, row.source)
            for row in (
                await session.scalars(select(IndiaVix).order_by(IndiaVix.timestamp))
            ).all()
        ],
    }


async def test_seed_populates_the_expected_shape(clean_database: None) -> None:
    """One instrument, one target, and a row per elapsed trading day."""
    summary = await seed_database(_YEAR, _MONTH, through=_THROUGH)

    expected_days = len(elapsed_trading_days(_YEAR, _MONTH, _THROUGH))

    assert summary.trading_days == expected_days
    assert summary.instruments == 1
    assert summary.sessions == expected_days
    assert summary.candles == expected_days
    assert summary.vix_points == expected_days


async def test_seed_writes_only_weekdays(clean_database: None) -> None:
    """NSE does not trade on Saturday or Sunday.

    A seeded weekend session would show up on the dashboard calendar as a
    trading day, which is a visible lie about when the market is open.
    """
    await seed_database(_YEAR, _MONTH, through=_THROUGH)

    async with session_scope() as session:
        dates = (await session.scalars(select(DailyPerformance.trading_date))).all()

    assert dates
    assert all(day.weekday() < 5 for day in dates), sorted(dates)


async def test_seed_writes_no_future_dates(clean_database: None) -> None:
    """The seed describes days that have happened, not days that have not.

    Recording a result for a date that has not occurred is the one thing a
    trading journal must never do — it is indistinguishable in shape from a
    look-ahead bug, and a backtest built on such a table would report an edge
    that does not exist.
    """
    await seed_database(_YEAR, _MONTH, through=_THROUGH)

    async with session_scope() as session:
        latest = await session.scalar(select(func.max(DailyPerformance.trading_date)))

    assert latest is not None
    assert latest <= _THROUGH


async def test_every_seeded_row_is_marked_as_invented(clean_database: None) -> None:
    """§46: provenance is per row, so invented data stays traceable.

    Checked across all three source-bearing tables rather than one, because a
    single unmarked table is enough to let fabricated figures pass as real.
    """
    await seed_database(_YEAR, _MONTH, through=_THROUGH)

    async with session_scope() as session:
        for model in (DailyPerformance, MarketInstrument, OhlcvCandle, IndiaVix):
            sources = set((await session.scalars(select(model.source))).all())
            assert sources == {SEED_SOURCE}, (model.__tablename__, sources)


async def test_seed_is_idempotent(clean_database: None) -> None:
    """Re-running must converge, not accumulate.

    Deliberately asserted on the *second* run rather than on a count after one
    run: the failure this guards against — `INSERT` without `ON CONFLICT` —
    only appears on the repeat.
    """
    await seed_database(_YEAR, _MONTH, through=_THROUGH)
    async with session_scope() as session:
        first = await _snapshot(session)

    await seed_database(_YEAR, _MONTH, through=_THROUGH)
    async with session_scope() as session:
        second = await _snapshot(session)

    assert second == first


async def test_reseeding_does_not_grow_the_audit_log(clean_database: None) -> None:
    """A re-run is not a target change.

    The history table exists to explain why the target is what it is. If every
    seed run appended to it, that explanation would be buried.
    """
    await seed_database(_YEAR, _MONTH, through=_THROUGH)
    await seed_database(_YEAR, _MONTH, through=_THROUGH)

    async with session_scope() as session:
        entries = await session.scalar(
            select(func.count()).select_from(MonthlyTargetHistory)
        )

    assert entries == 1


async def test_reseeding_never_overwrites_a_user_edit(clean_database: None) -> None:
    """A developer's own target must survive the next `python -m app.db.seed`.

    The seed inserts the target with `ON CONFLICT DO NOTHING`, not `DO UPDATE`.
    Reaching for the more obvious upsert would silently revert a deliberate
    change every time the seed ran — the kind of behaviour that gets diagnosed
    as "the dashboard keeps forgetting my target".
    """
    await seed_database(_YEAR, _MONTH, through=_THROUGH)

    async with session_scope() as session:
        target = (
            await session.scalars(
                select(MonthlyTarget).where(
                    MonthlyTarget.year == _YEAR, MonthlyTarget.month == _MONTH
                )
            )
        ).one()
        assert target.target_amount == SEED_MONTHLY_TARGET
        target.target_amount = Decimal("31337.00")

    await seed_database(_YEAR, _MONTH, through=_THROUGH)

    async with session_scope() as session:
        amount = await session.scalar(
            select(MonthlyTarget.target_amount).where(
                MonthlyTarget.year == _YEAR, MonthlyTarget.month == _MONTH
            )
        )

    assert amount == Decimal("31337.00")
