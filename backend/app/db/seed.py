"""Development seed data.

    python -m app.db.seed

Populates an empty database with a coherent month of invented trading activity
so the dashboard has something to render, and so the time-series tables are
exercised rather than merely created.

EVERYTHING HERE IS FABRICATED
-----------------------------
No figure below came from an exchange, a broker or a feed. Every row is written
with `source = development_seed`, which is a distinct value from `nse` and
`broker` precisely so invented data can never be mistaken for the real thing at
query time. The API additionally reports `source` on every payload built from
these rows. Nothing in this module may ever write `nse`.

DETERMINISTIC
-------------
No randomness, no clock reads below the anchor month, no auto-increment keys.
Primary keys are UUIDv5 values derived from each row's natural key, so seeding
a wiped database reproduces byte-identical rows — the same trading date always
gets the same UUID. That makes a seeded database diffable, which a `random()`
or `uuid4()` seed never is.

IDEMPOTENT
----------
Every write is an upsert on the row's natural key, so running the seed twice
leaves exactly the same rows as running it once. It is safe against a database
that is already seeded, partially seeded, or seeded by an older version of this
file. It does not delete anything it did not write, and it never truncates.

WHY NOT SEED THE FUTURE
-----------------------
Sessions are written only for trading days that have already elapsed. A seed
that filled in the rest of the month would put realized P&L against dates that
have not happened yet — a fabricated figure sitting in a column that everything
downstream reads as settled fact.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import CURRENCY, IST
from app.core.logging import configure_logging, get_logger
from app.db.models.daily_performance import DailyPerformance
from app.db.models.instrument import MarketInstrument
from app.db.models.market_data import IndiaVix, OhlcvCandle
from app.db.models.monthly_target import MonthlyTarget, MonthlyTargetHistory
from app.db.session import dispose_engine, session_scope
from app.domain.calculations import calculate_daily_target
from app.domain.clock import current_period, month_bounds, today_ist
from app.domain.enums import (
    CalculationMode,
    DataSource,
    InstrumentType,
    TargetChangeSource,
    Timeframe,
)

logger = get_logger(__name__)

#: Provenance written to every row this module creates.
SEED_SOURCE: Final = DataSource.DEVELOPMENT_SEED.value

#: Namespace for UUIDv5 keys. A fixed, arbitrary UUID — its only job is to keep
#: seed-derived identifiers from colliding with any other UUIDv5 scheme.
_SEED_NAMESPACE: Final = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

#: The monthly goal a fresh development database starts with. ₹15,000 is the
#: figure the Phase 3 persistence check uses, so a seeded database and that
#: check tell the same story.
SEED_MONTHLY_TARGET: Final = Decimal("15000.00")

#: NSE cash session open, used as the daily bar's open time.
_SESSION_OPEN_TIME: Final = dt.time(9, 15)


def _seed_uuid(*parts: object) -> uuid.UUID:
    """A stable identifier derived from a row's natural key."""
    return uuid.uuid5(_SEED_NAMESPACE, ":".join(str(part) for part in parts))


@dataclass(frozen=True, slots=True)
class SessionShape:
    """One trading day's invented outcome.

    Fixed rather than generated so the dataset covers every state the calendar
    can render — target beaten, profit below target, loss, and a recorded
    no-trade day — instead of whatever a random walk happened to produce.
    """

    realized_pnl: str
    trades: int
    wins: int
    losses: int


#: Mirrors the Phase 1 frontend fixture, so the dashboard reads the same whether
#: it renders from the bundled mock or from a seeded database. Cycled if a month
#: has more elapsed trading days than there are entries.
_SESSION_SHAPES: Final[tuple[SessionShape, ...]] = (
    SessionShape("410.00", 3, 2, 1),
    SessionShape("185.00", 2, 1, 1),
    SessionShape("-240.00", 3, 1, 2),
    SessionShape("520.00", 4, 3, 1),
    SessionShape("0.00", 0, 0, 0),
    SessionShape("365.00", 2, 2, 0),
    SessionShape("295.00", 3, 2, 1),
    SessionShape("-150.00", 2, 0, 2),
    SessionShape("610.00", 4, 3, 1),
    SessionShape("340.00", 3, 2, 1),
    SessionShape("95.00", 2, 1, 1),
    SessionShape("-310.00", 3, 1, 2),
    SessionShape("455.00", 3, 2, 1),
    SessionShape("825.00", 5, 4, 1),
    SessionShape("460.00", 3, 2, 1),
    SessionShape("420.00", 3, 2, 1),
)

#: Per-trade brokerage and statutory charges, as a flat invented figure. Real
#: charges are a function of turnover, segment and several statutory rates;
#: modelling that properly belongs with real fills, not with a seed.
_FEE_PER_TRADE: Final = Decimal("21.50")

_NIFTY_SYMBOL: Final = "NIFTY 50"


@dataclass(frozen=True, slots=True)
class SeedSummary:
    """What a seed run touched, for the closing log line."""

    trading_days: int
    instruments: int
    sessions: int
    candles: int
    vix_points: int


def elapsed_trading_days(year: int, month: int, through: dt.date) -> list[dt.date]:
    """Weekdays of the month up to and including `through`.

    Saturdays and Sundays are excluded because NSE does not trade them. NSE
    holidays are *not* excluded: no holiday calendar is ingested in this phase,
    and inventing one would be a guess baked into a database. The consequence
    is a seeded session on the occasional public holiday, which is visible,
    harmless in development, and disappears once a real calendar exists.
    """
    start, end = month_bounds(year, month)
    last = min(end - dt.timedelta(days=1), through)

    days: list[dt.date] = []
    day = start
    while day <= last:
        if day.weekday() < 5:  # Monday..Friday
            days.append(day)
        day += dt.timedelta(days=1)
    return days


def _nifty_close(index: int) -> Decimal:
    """A deterministic price path around a plausible NIFTY level.

    Integer arithmetic rather than a seeded PRNG: the values are reproducible
    across Python versions and platforms, and a reader can verify any single
    day by hand.
    """
    return Decimal(25_000 + (index * 137) % 601 - 300)


def _vix_close(index: int) -> Decimal:
    """A deterministic India VIX path, in the low-to-mid teens."""
    return Decimal("12.50") + Decimal((index * 7) % 41) / Decimal(10)


async def _seed_instruments(session: AsyncSession) -> int:
    """Insert the NIFTY 50 index row.

    Only the index. Futures and option contracts have expiries and strikes that
    are exchange facts, and fabricating a contract that never existed would put
    a plausible-looking lie in the instrument master — the one table whose job
    is to say what a symbol really is.
    """
    statement = (
        insert(MarketInstrument)
        .values(
            id=_seed_uuid("market_instrument", "NSE", _NIFTY_SYMBOL),
            exchange="NSE",
            segment="NSE",
            symbol=_NIFTY_SYMBOL,
            underlying="NIFTY",
            instrument_type=InstrumentType.INDEX.value,
            # An index is not tradable: no lot, no tick, no expiry. The
            # `index_fields_empty` CHECK enforces exactly this shape.
            lot_size=None,
            tick_size=None,
            expiry=None,
            strike_price=None,
            option_type=None,
            active=True,
            source=SEED_SOURCE,
        )
        .on_conflict_do_nothing(constraint="uq_market_instruments_exchange_symbol")
    )
    await session.execute(statement)
    return 1


async def _seed_monthly_target(session: AsyncSession, year: int, month: int) -> None:
    """Set the month's goal, appending history only on a real change.

    Re-running the seed must not grow the audit log. `monthly_target_history`
    is append-only evidence of what the user changed; a row saying
    "₹15,000 became ₹15,000" is not evidence of anything, and a hundred of them
    would bury the entries that matter.
    """
    target_id = _seed_uuid("monthly_target", year, month)

    statement = (
        insert(MonthlyTarget)
        .values(
            id=target_id,
            year=year,
            month=month,
            target_amount=SEED_MONTHLY_TARGET,
            currency=CURRENCY,
            calculation_mode=CalculationMode.CALENDAR_DAYS_30.value,
        )
        .on_conflict_do_nothing(constraint="uq_monthly_targets_year_month")
        .returning(MonthlyTarget.id)
    )
    inserted = (await session.execute(statement)).scalar_one_or_none()

    if inserted is None:
        # The row already existed — possibly with a target the developer set by
        # hand through the dashboard. Leave it alone. A seed that overwrote it
        # would silently undo the user's own edit on every run.
        return

    session.add(
        MonthlyTargetHistory(
            id=_seed_uuid("monthly_target_history", year, month),
            monthly_target_id=target_id,
            previous_amount=None,
            new_amount=SEED_MONTHLY_TARGET,
            source=TargetChangeSource.DEVELOPMENT_SEED.value,
        )
    )


async def _seed_sessions(session: AsyncSession, days: list[dt.date]) -> int:
    """Write one `daily_performance` row per elapsed trading day."""
    daily_target = Decimal(calculate_daily_target(SEED_MONTHLY_TARGET))

    for index, day in enumerate(days):
        shape = _SESSION_SHAPES[index % len(_SESSION_SHAPES)]
        realized = Decimal(shape.realized_pnl)
        fees = _FEE_PER_TRADE * shape.trades

        statement = insert(DailyPerformance).values(
            id=_seed_uuid("daily_performance", day.isoformat()),
            trading_date=day,
            realized_pnl=realized,
            unrealized_pnl=None,
            fees=fees,
            net_pnl=realized - fees,
            daily_target=daily_target,
            trade_count=shape.trades,
            win_count=shape.wins,
            loss_count=shape.losses,
            breakeven_count=shape.trades - shape.wins - shape.losses,
            source=SEED_SOURCE,
        )
        # Update on conflict rather than skip, so a change to the shapes above
        # is picked up by re-running the seed instead of requiring a wipe.
        await session.execute(
            statement.on_conflict_do_update(
                constraint="uq_daily_performance_trading_date",
                set_={
                    "realized_pnl": statement.excluded.realized_pnl,
                    "fees": statement.excluded.fees,
                    "net_pnl": statement.excluded.net_pnl,
                    "daily_target": statement.excluded.daily_target,
                    "trade_count": statement.excluded.trade_count,
                    "win_count": statement.excluded.win_count,
                    "loss_count": statement.excluded.loss_count,
                    "breakeven_count": statement.excluded.breakeven_count,
                    "source": statement.excluded.source,
                },
            )
        )

    return len(days)


async def _seed_market_data(
    session: AsyncSession, days: list[dt.date]
) -> tuple[int, int]:
    """Write one daily NIFTY bar and one India VIX point per trading day.

    Enough to prove the hypertables accept writes, serve reads and prune by
    chunk — an empty hypertable demonstrates none of that. Daily bars only:
    a minute series would be tens of thousands of invented prices, and the
    volume of a lie does not improve it.
    """
    instrument_id = _seed_uuid("market_instrument", "NSE", _NIFTY_SYMBOL)

    for index, day in enumerate(days):
        opened_at = dt.datetime.combine(day, _SESSION_OPEN_TIME, tzinfo=IST)

        close = _nifty_close(index)
        open_ = close - Decimal(25)
        high = max(open_, close) + Decimal(40)
        low = min(open_, close) - Decimal(35)

        candle = insert(OhlcvCandle).values(
            timestamp=opened_at,
            instrument_id=instrument_id,
            timeframe=Timeframe.D1.value,
            source=SEED_SOURCE,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=250_000_000 + (index * 1_700_000) % 90_000_000,
            # An index has no open interest.
            open_interest=None,
        )
        await session.execute(
            candle.on_conflict_do_update(
                index_elements=["timestamp", "instrument_id", "timeframe", "source"],
                set_={
                    "open": candle.excluded.open,
                    "high": candle.excluded.high,
                    "low": candle.excluded.low,
                    "close": candle.excluded.close,
                    "volume": candle.excluded.volume,
                },
            )
        )

        vix_close = _vix_close(index)
        vix_open = vix_close - Decimal("0.35")
        vix = insert(IndiaVix).values(
            timestamp=opened_at,
            source=SEED_SOURCE,
            open=vix_open,
            high=max(vix_open, vix_close) + Decimal("0.60"),
            low=min(vix_open, vix_close) - Decimal("0.45"),
            close=vix_close,
        )
        await session.execute(
            vix.on_conflict_do_update(
                index_elements=["timestamp", "source"],
                set_={
                    "open": vix.excluded.open,
                    "high": vix.excluded.high,
                    "low": vix.excluded.low,
                    "close": vix.excluded.close,
                },
            )
        )

    return len(days), len(days)


async def seed_database(
    year: int | None = None,
    month: int | None = None,
    through: dt.date | None = None,
) -> SeedSummary:
    """Seed one month, in a single transaction.

    All-or-nothing: a failure part way through leaves the database exactly as
    it was, rather than half-seeded in a way that the idempotency logic would
    then have to reason about.
    """
    default_year, default_month = current_period()
    year = year if year is not None else default_year
    month = month if month is not None else default_month
    through = through if through is not None else today_ist()

    days = elapsed_trading_days(year, month, through)

    async with session_scope() as session:
        instruments = await _seed_instruments(session)
        await _seed_monthly_target(session, year, month)
        # Instruments must land before candles: `ohlcv_candles.instrument_id`
        # is a real foreign key, not a loose reference.
        await session.flush()
        sessions = await _seed_sessions(session, days)
        candles, vix_points = await _seed_market_data(session, days)

    return SeedSummary(
        trading_days=len(days),
        instruments=instruments,
        sessions=sessions,
        candles=candles,
        vix_points=vix_points,
    )


def _describe(summary: SeedSummary, year: int, month: int) -> None:
    logger.info(
        "seed_complete period=%04d-%02d trading_days=%d instruments=%d "
        "sessions=%d candles=%d vix_points=%d source=%s",
        year,
        month,
        summary.trading_days,
        summary.instruments,
        summary.sessions,
        summary.candles,
        summary.vix_points,
        SEED_SOURCE,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.db.seed",
        description=(
            "Populate the development database with deterministic, clearly "
            "labelled sample data. Safe to run repeatedly."
        ),
    )
    parser.add_argument(
        "--year", type=int, default=None, help="Year to seed. Defaults to the current."
    )
    parser.add_argument(
        "--month",
        type=int,
        choices=range(1, 13),
        default=None,
        metavar="1-12",
        help="Month to seed. Defaults to the current.",
    )
    return parser.parse_args(argv)


async def _main_async(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = get_settings()
    configure_logging(settings)

    logger.info("seed_started target=%s", settings.safe_database_url)
    try:
        summary = await seed_database(year=args.year, month=args.month)
        year, month = current_period()
        _describe(
            summary,
            args.year if args.year is not None else year,
            args.month if args.month is not None else month,
        )
    finally:
        await dispose_engine()


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main_async(argv))


if __name__ == "__main__":
    main()
