"""initial schema

Creates the whole Phase 3 data foundation in one revision, in the only order
that works:

1. extensions   -- TimescaleDB must exist before any hypertable is created
2. tables       -- plain PostgreSQL tables, in dependency order
3. indexes      -- including the partial unique indexes
4. hypertables  -- converts the three time-series tables in place

Steps 1-3 are Alembic autogenerate output. Step 4 is hand-written: autogenerate
has no concept of a hypertable and will never emit it.

REVERSIBILITY
-------------
`downgrade()` drops every table, which also removes the hypertable definitions
and their chunks -- converting a hypertable back to a plain table is not a
supported operation, so there is nothing finer-grained to undo. The
`timescaledb` extension is deliberately NOT dropped: it is database-wide, may
predate this application, and dropping it would cascade into any other schema
using it.

Revision ID: 097a184c6dd8
Revises:
Create Date: 2026-09-23 03:47:00.467887+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "097a184c6dd8"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: Chunk interval per hypertable, chosen from expected write volume rather than
#: copied from a tutorial. Timescale's guidance is that a chunk's indexes should
#: fit comfortably in memory; too small a chunk multiplies planning overhead,
#: too large a one defeats chunk exclusion.
#:
#: - option_quotes: the firehose. One NIFTY expiry is ~100+ strikes x 2 rights,
#:   sampled through a 6h15m session -> order of 10^5 rows/day. One day/chunk.
#: - ohlcv_candles: a few thousand rows/day across instruments and timeframes,
#:   three orders of magnitude lighter, so a week per chunk avoids thousands of
#:   near-empty chunks.
#: - india_vix: a single series, a handful of rows per day. A month per chunk.
_HYPERTABLES: list[tuple[str, str, str]] = [
    ("ohlcv_candles", "timestamp", "7 days"),
    ("option_quotes", "timestamp", "1 day"),
    ("india_vix", "timestamp", "30 days"),
]


def _create_timescaledb_extension() -> None:
    """Enable TimescaleDB, failing loudly and usefully if it is unavailable.

    The bare `CREATE EXTENSION` error ("extension \"timescaledb\" is not
    available") does not tell an operator that they are pointed at a stock
    PostgreSQL image instead of a Timescale one, which is the actual cause
    essentially every time.
    """
    bind = op.get_bind()
    available = bind.execute(
        sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'")
    ).scalar()

    if available is None:
        raise RuntimeError(
            "The 'timescaledb' extension is not available on this PostgreSQL "
            "server, so the time-series tables cannot be created.\n"
            "This almost always means the database is a stock 'postgres' "
            "image rather than a 'timescale/timescaledb' one.\n"
            "Start the bundled stack with: docker compose up -d"
        )

    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")


def _create_hypertables() -> None:
    """Convert the time-series tables into TimescaleDB hypertables.

    Every one of these tables has its partitioning column as the leading member
    of its primary key. That is a hard TimescaleDB requirement, not a style
    choice: a unique index on a hypertable must contain the partitioning
    column, because uniqueness is only enforced within a chunk.

    `migrate_data => FALSE` is correct and intentional -- these tables are
    created empty microseconds earlier in this same migration, so there is
    nothing to migrate, and passing TRUE would only add a pointless scan.

    The `by_range(...)` dimension form is used rather than the older
    `create_hypertable(relation, 'column', chunk_time_interval => ...)`
    positional form. Both overloads are present on this server, which makes an
    uncast argument genuinely ambiguous between `name` and `dimension_info`;
    the casts below pick the modern, non-deprecated overload explicitly.

    `create_default_indexes => FALSE` is deliberate, for two reasons:

    1. Redundancy. Timescale's default is an index on the partitioning column
       alone (`<table>_timestamp_idx`). All three tables here already have
       `timestamp` as the LEADING column of their primary key, so that index
       duplicates the PK index -- paying storage and per-insert maintenance on
       `option_quotes`, the heaviest write path in the schema, for nothing.
    2. Schema drift. An index Timescale creates behind Alembic's back is absent
       from the ORM metadata, so the next `--autogenerate` run faithfully
       proposes dropping it. Owning every index explicitly keeps
       `alembic check` clean and meaningful.
    """
    for table, column, interval in _HYPERTABLES:
        op.execute(
            sa.text(
                "SELECT create_hypertable("
                "  CAST(:table AS regclass),"
                "  by_range(CAST(:column AS name), CAST(:interval AS INTERVAL)),"
                "  if_not_exists => TRUE,"
                "  migrate_data => FALSE,"
                "  create_default_indexes => FALSE"
                ")"
            ).bindparams(table=table, column=column, interval=interval)
        )


def upgrade() -> None:
    # Step 1: extensions. Must precede every table, because the hypertable
    # conversions at the end of this function depend on it.
    _create_timescaledb_extension()

    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "daily_performance",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("fees", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("net_pnl", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("daily_target", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("trade_count", sa.Integer(), nullable=False),
        sa.Column("win_count", sa.Integer(), nullable=False),
        sa.Column("loss_count", sa.Integer(), nullable=False),
        sa.Column("breakeven_count", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('broker', 'database', 'development_seed', 'mock', 'nse', 'simulation')",
            name=op.f("ck_daily_performance_source"),
        ),
        sa.CheckConstraint(
            "breakeven_count >= 0", name=op.f("ck_daily_performance_breakeven_count")
        ),
        sa.CheckConstraint(
            "fees >= 0", name=op.f("ck_daily_performance_fees_non_negative")
        ),
        sa.CheckConstraint(
            "loss_count >= 0", name=op.f("ck_daily_performance_loss_count")
        ),
        sa.CheckConstraint(
            "trade_count >= 0", name=op.f("ck_daily_performance_trade_count")
        ),
        sa.CheckConstraint(
            "win_count + loss_count + breakeven_count <= trade_count",
            name=op.f("ck_daily_performance_outcomes_within_trades"),
        ),
        sa.CheckConstraint(
            "win_count >= 0", name=op.f("ck_daily_performance_win_count")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_performance")),
        sa.UniqueConstraint("trading_date", name="uq_daily_performance_trading_date"),
    )
    op.create_table(
        "india_vix",
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("open", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("high", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("low", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("close", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('broker', 'database', 'development_seed', 'mock', 'nse', 'simulation')",
            name=op.f("ck_india_vix_source"),
        ),
        sa.CheckConstraint(
            "high >= low AND high >= open AND high >= close AND low <= open AND low <= close",
            name=op.f("ck_india_vix_ohlc_coherent"),
        ),
        sa.CheckConstraint(
            "open > 0 AND high > 0 AND low > 0 AND close > 0",
            name=op.f("ck_india_vix_prices_positive"),
        ),
        sa.PrimaryKeyConstraint("timestamp", "source", name=op.f("pk_india_vix")),
    )
    op.create_table(
        "market_instruments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column("segment", sa.String(length=16), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("underlying", sa.String(length=32), nullable=False),
        sa.Column("instrument_type", sa.String(length=16), nullable=False),
        sa.Column("exchange_token", sa.String(length=32), nullable=True),
        sa.Column("lot_size", sa.Integer(), nullable=True),
        sa.Column("tick_size", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("expiry", sa.Date(), nullable=True),
        sa.Column("strike_price", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("option_type", sa.String(length=2), nullable=True),
        sa.Column(
            "active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(instrument_type <> 'FUTURE') OR (expiry IS NOT NULL AND strike_price IS NULL AND option_type IS NULL)",
            name=op.f("ck_market_instruments_future_fields_complete"),
        ),
        sa.CheckConstraint(
            "(instrument_type <> 'INDEX') OR (expiry IS NULL AND strike_price IS NULL AND option_type IS NULL)",
            name=op.f("ck_market_instruments_index_fields_empty"),
        ),
        sa.CheckConstraint(
            "(instrument_type <> 'OPTION') OR (expiry IS NOT NULL AND strike_price IS NOT NULL AND option_type IS NOT NULL)",
            name=op.f("ck_market_instruments_option_fields_complete"),
        ),
        sa.CheckConstraint(
            "instrument_type IN ('FUTURE', 'INDEX', 'OPTION')",
            name=op.f("ck_market_instruments_instrument_type"),
        ),
        sa.CheckConstraint(
            "option_type IS NULL OR option_type IN ('CE', 'PE')",
            name=op.f("ck_market_instruments_option_type"),
        ),
        sa.CheckConstraint(
            "source IN ('broker', 'database', 'development_seed', 'mock', 'nse', 'simulation')",
            name=op.f("ck_market_instruments_source"),
        ),
        sa.CheckConstraint(
            "lot_size IS NULL OR lot_size > 0",
            name=op.f("ck_market_instruments_lot_size_positive"),
        ),
        sa.CheckConstraint(
            "strike_price IS NULL OR strike_price > 0",
            name=op.f("ck_market_instruments_strike_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_instruments")),
        sa.UniqueConstraint(
            "exchange", "symbol", name="uq_market_instruments_exchange_symbol"
        ),
    )
    op.create_index(
        "ix_market_instruments_underlying_expiry",
        "market_instruments",
        ["underlying", "expiry"],
        unique=False,
        postgresql_where=sa.text("active"),
    )
    op.create_index(
        "uq_market_instruments_contract",
        "market_instruments",
        ["exchange", "underlying", "expiry", "strike_price", "option_type"],
        unique=True,
        postgresql_where=sa.text("instrument_type = 'OPTION'"),
    )
    op.create_index(
        "uq_market_instruments_future_contract",
        "market_instruments",
        ["exchange", "underlying", "expiry"],
        unique=True,
        postgresql_where=sa.text("instrument_type = 'FUTURE'"),
    )
    op.create_table(
        "monthly_targets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("month", sa.SmallInteger(), nullable=False),
        sa.Column("target_amount", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("calculation_mode", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "calculation_mode IN ('calendar_days_30', 'nse_trading_sessions')",
            name=op.f("ck_monthly_targets_calculation_mode"),
        ),
        sa.CheckConstraint(
            "month BETWEEN 1 AND 12", name=op.f("ck_monthly_targets_month")
        ),
        sa.CheckConstraint(
            "target_amount > 0", name=op.f("ck_monthly_targets_amount_positive")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monthly_targets")),
        sa.UniqueConstraint("year", "month", name="uq_monthly_targets_year_month"),
    )
    op.create_table(
        "option_chain_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("underlying", sa.String(length=32), nullable=False),
        sa.Column("spot_price", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('broker', 'database', 'development_seed', 'mock', 'nse', 'simulation')",
            name=op.f("ck_option_chain_snapshots_source"),
        ),
        sa.CheckConstraint(
            "spot_price > 0", name=op.f("ck_option_chain_snapshots_spot_positive")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_option_chain_snapshots")),
        sa.UniqueConstraint(
            "underlying",
            "expiry",
            "captured_at",
            "source",
            name="uq_option_chain_snapshots_identity",
        ),
    )
    op.create_index(
        "ix_option_chain_snapshots_underlying_captured",
        "option_chain_snapshots",
        ["underlying", "captured_at"],
        unique=False,
    )
    op.create_table(
        "trading_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("market", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('closed', 'disabled', 'holiday', 'open', 'scheduled')",
            name=op.f("ck_trading_sessions_status"),
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR started_at IS NULL OR ended_at >= started_at",
            name=op.f("ck_trading_sessions_end_after_start"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trading_sessions")),
        sa.UniqueConstraint(
            "trading_date", "market", name="uq_trading_sessions_trading_date_market"
        ),
    )
    op.create_table(
        "monthly_target_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("monthly_target_id", sa.UUID(), nullable=False),
        sa.Column("previous_amount", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("new_amount", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "source IN ('development_seed', 'user')",
            name=op.f("ck_monthly_target_history_source"),
        ),
        sa.CheckConstraint(
            "new_amount > 0", name=op.f("ck_monthly_target_history_new_amount_positive")
        ),
        sa.ForeignKeyConstraint(
            ["monthly_target_id"],
            ["monthly_targets.id"],
            name=op.f("fk_monthly_target_history_monthly_target_id_monthly_targets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monthly_target_history")),
    )
    op.create_index(
        op.f("ix_monthly_target_history_monthly_target_id"),
        "monthly_target_history",
        ["monthly_target_id"],
        unique=False,
    )
    op.create_table(
        "ohlcv_candles",
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("open", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("high", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("low", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("close", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("open_interest", sa.BigInteger(), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('broker', 'database', 'development_seed', 'mock', 'nse', 'simulation')",
            name=op.f("ck_ohlcv_candles_source"),
        ),
        sa.CheckConstraint(
            "timeframe IN ('15m', '1d', '1h', '1m', '30m', '3m', '5m')",
            name=op.f("ck_ohlcv_candles_timeframe"),
        ),
        sa.CheckConstraint(
            "high >= low AND high >= open AND high >= close AND low <= open AND low <= close",
            name=op.f("ck_ohlcv_candles_ohlc_coherent"),
        ),
        sa.CheckConstraint(
            "open > 0 AND high > 0 AND low > 0 AND close > 0",
            name=op.f("ck_ohlcv_candles_prices_positive"),
        ),
        sa.CheckConstraint(
            "open_interest IS NULL OR open_interest >= 0",
            name=op.f("ck_ohlcv_candles_open_interest_non_negative"),
        ),
        sa.CheckConstraint(
            "volume >= 0", name=op.f("ck_ohlcv_candles_volume_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["market_instruments.id"],
            name=op.f("fk_ohlcv_candles_instrument_id_market_instruments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "timestamp",
            "instrument_id",
            "timeframe",
            "source",
            name=op.f("pk_ohlcv_candles"),
        ),
    )
    op.create_index(
        "ix_ohlcv_candles_instrument_timeframe_time",
        "ohlcv_candles",
        ["instrument_id", "timeframe", sa.literal_column('"timestamp" DESC')],
        unique=False,
    )
    op.create_table(
        "option_quotes",
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("snapshot_id", sa.UUID(), nullable=False),
        sa.Column("strike_price", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("option_type", sa.String(length=2), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("last_price", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("bid_price", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("ask_price", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("bid_quantity", sa.BigInteger(), nullable=True),
        sa.Column("ask_quantity", sa.BigInteger(), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("open_interest", sa.BigInteger(), nullable=True),
        sa.Column("change_in_open_interest", sa.BigInteger(), nullable=True),
        sa.Column(
            "implied_volatility", sa.Numeric(precision=12, scale=6), nullable=True
        ),
        sa.Column("delta", sa.Numeric(precision=16, scale=8), nullable=True),
        sa.Column("gamma", sa.Numeric(precision=16, scale=8), nullable=True),
        sa.Column("theta", sa.Numeric(precision=16, scale=8), nullable=True),
        sa.Column("vega", sa.Numeric(precision=16, scale=8), nullable=True),
        sa.Column("rho", sa.Numeric(precision=16, scale=8), nullable=True),
        sa.Column("underlying_price", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "option_type IN ('CE', 'PE')", name=op.f("ck_option_quotes_option_type")
        ),
        sa.CheckConstraint(
            "source IN ('broker', 'database', 'development_seed', 'mock', 'nse', 'simulation')",
            name=op.f("ck_option_quotes_source"),
        ),
        sa.CheckConstraint(
            "ask_price IS NULL OR ask_price >= 0",
            name=op.f("ck_option_quotes_ask_non_negative"),
        ),
        sa.CheckConstraint(
            "bid_price IS NULL OR bid_price >= 0",
            name=op.f("ck_option_quotes_bid_non_negative"),
        ),
        sa.CheckConstraint(
            "delta IS NULL OR (delta >= -1 AND delta <= 1)",
            name=op.f("ck_option_quotes_delta_bounded"),
        ),
        sa.CheckConstraint(
            "implied_volatility IS NULL OR implied_volatility >= 0",
            name=op.f("ck_option_quotes_iv_non_negative"),
        ),
        sa.CheckConstraint(
            "last_price IS NULL OR last_price >= 0",
            name=op.f("ck_option_quotes_last_price_non_negative"),
        ),
        sa.CheckConstraint(
            "open_interest IS NULL OR open_interest >= 0",
            name=op.f("ck_option_quotes_open_interest_non_negative"),
        ),
        sa.CheckConstraint(
            "strike_price > 0", name=op.f("ck_option_quotes_strike_positive")
        ),
        sa.CheckConstraint(
            "volume IS NULL OR volume >= 0",
            name=op.f("ck_option_quotes_volume_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["market_instruments.id"],
            name=op.f("fk_option_quotes_instrument_id_market_instruments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["option_chain_snapshots.id"],
            name=op.f("fk_option_quotes_snapshot_id_option_chain_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "timestamp", "instrument_id", "source", name=op.f("pk_option_quotes")
        ),
    )
    op.create_index(
        "ix_option_quotes_expiry_time_strike",
        "option_quotes",
        ["expiry", "timestamp", "strike_price", "option_type"],
        unique=False,
    )
    op.create_index(
        "ix_option_quotes_instrument_time",
        "option_quotes",
        ["instrument_id", sa.literal_column('"timestamp" DESC')],
        unique=False,
    )
    op.create_index(
        "ix_option_quotes_snapshot", "option_quotes", ["snapshot_id"], unique=False
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("broker", sa.String(length=32), nullable=True),
        sa.Column("broker_order_id", sa.String(length=64), nullable=True),
        sa.Column("client_order_id", sa.String(length=64), nullable=True),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("order_type", sa.String(length=24), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("trigger_price", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("strategy_name", sa.String(length=64), nullable=True),
        sa.Column("strategy_version", sa.String(length=32), nullable=True),
        sa.Column("signal_id", sa.UUID(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "broker_raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "order_type IN ('limit', 'market', 'stop_loss', 'stop_loss_market')",
            name=op.f("ck_orders_order_type"),
        ),
        sa.CheckConstraint("side IN ('buy', 'sell')", name=op.f("ck_orders_side")),
        sa.CheckConstraint(
            "status IN ('cancelled', 'expired', 'filled', 'open', 'partially_filled', 'pending', 'rejected', 'submitted')",
            name=op.f("ck_orders_status"),
        ),
        sa.CheckConstraint(
            "price IS NULL OR price >= 0", name=op.f("ck_orders_price_non_negative")
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_orders_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["market_instruments.id"],
            name=op.f("fk_orders_instrument_id_market_instruments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
    )
    op.create_index(
        "ix_orders_instrument_created",
        "orders",
        ["instrument_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_orders_status", "orders", ["status"], unique=False)
    op.create_index(
        "uq_orders_broker_order_id",
        "orders",
        ["broker", "broker_order_id"],
        unique=True,
        postgresql_where=sa.text("broker_order_id IS NOT NULL"),
    )
    op.create_table(
        "positions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "average_entry_price", sa.Numeric(precision=20, scale=4), nullable=False
        ),
        sa.Column("realized_pnl", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'closed' AND closed_at IS NOT NULL) OR (status <> 'closed' AND closed_at IS NULL)",
            name=op.f("ck_positions_closed_at_matches_status"),
        ),
        sa.CheckConstraint(
            "status IN ('closed', 'open')", name=op.f("ck_positions_status")
        ),
        sa.CheckConstraint(
            "average_entry_price >= 0", name=op.f("ck_positions_avg_price_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["market_instruments.id"],
            name=op.f("fk_positions_instrument_id_market_instruments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_positions")),
    )
    op.create_index("ix_positions_status", "positions", ["status"], unique=False)
    op.create_index(
        "uq_positions_open_instrument",
        "positions",
        ["instrument_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_table(
        "executions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("broker_execution_id", sa.String(length=64), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("fees", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("fees >= 0", name=op.f("ck_executions_fees_non_negative")),
        sa.CheckConstraint("price >= 0", name=op.f("ck_executions_price_non_negative")),
        sa.CheckConstraint(
            "quantity > 0", name=op.f("ck_executions_quantity_positive")
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_executions_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_executions")),
        sa.UniqueConstraint(
            "order_id",
            "broker_execution_id",
            name="uq_executions_order_broker_execution",
        ),
    )
    op.create_index(
        "ix_executions_executed_at", "executions", ["executed_at"], unique=False
    )
    op.create_index("ix_executions_order", "executions", ["order_id"], unique=False)
    op.create_table(
        "trades",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=True),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("exit_price", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("gross_pnl", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("fees", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("net_pnl", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_reason", sa.String(length=64), nullable=True),
        sa.Column("strategy_name", sa.String(length=64), nullable=True),
        sa.Column("strategy_version", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("side IN ('buy', 'sell')", name=op.f("ck_trades_side")),
        sa.CheckConstraint(
            "closed_at IS NULL OR closed_at >= opened_at",
            name=op.f("ck_trades_closed_after_opened"),
        ),
        sa.CheckConstraint(
            "entry_price >= 0", name=op.f("ck_trades_entry_price_non_negative")
        ),
        sa.CheckConstraint("fees >= 0", name=op.f("ck_trades_fees_non_negative")),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_trades_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["market_instruments.id"],
            name=op.f("fk_trades_instrument_id_market_instruments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_trades_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trades")),
    )
    op.create_index(
        "ix_trades_instrument_opened",
        "trades",
        ["instrument_id", "opened_at"],
        unique=False,
    )
    op.create_index("ix_trades_opened_at", "trades", ["opened_at"], unique=False)
    op.create_table(
        "trade_journal",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("trade_id", sa.UUID(), nullable=False),
        sa.Column("market_regime", sa.String(length=32), nullable=True),
        sa.Column("signal_type", sa.String(length=32), nullable=True),
        sa.Column("signal_confidence", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("entry_reason", sa.Text(), nullable=True),
        sa.Column("exit_reason", sa.Text(), nullable=True),
        sa.Column("diagnostic_category", sa.String(length=48), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "diagnostics", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "signal_confidence IS NULL OR (signal_confidence >= 0 AND signal_confidence <= 1)",
            name=op.f("ck_trade_journal_confidence_bounded"),
        ),
        sa.ForeignKeyConstraint(
            ["trade_id"],
            ["trades.id"],
            name=op.f("fk_trade_journal_trade_id_trades"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trade_journal")),
        sa.UniqueConstraint("trade_id", name="uq_trade_journal_trade_id"),
    )
    # ### end Alembic commands ###

    # Step 4: hypertables. Last, because a table must exist -- with its primary
    # key already in place -- before it can be converted.
    _create_hypertables()


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("trade_journal")
    op.drop_index("ix_trades_opened_at", table_name="trades")
    op.drop_index("ix_trades_instrument_opened", table_name="trades")
    op.drop_table("trades")
    op.drop_index("ix_executions_order", table_name="executions")
    op.drop_index("ix_executions_executed_at", table_name="executions")
    op.drop_table("executions")
    op.drop_index(
        "uq_positions_open_instrument",
        table_name="positions",
        postgresql_where=sa.text("status = 'open'"),
    )
    op.drop_index("ix_positions_status", table_name="positions")
    op.drop_table("positions")
    op.drop_index(
        "uq_orders_broker_order_id",
        table_name="orders",
        postgresql_where=sa.text("broker_order_id IS NOT NULL"),
    )
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_instrument_created", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_option_quotes_snapshot", table_name="option_quotes")
    op.drop_index("ix_option_quotes_instrument_time", table_name="option_quotes")
    op.drop_index("ix_option_quotes_expiry_time_strike", table_name="option_quotes")
    op.drop_table("option_quotes")
    op.drop_index(
        "ix_ohlcv_candles_instrument_timeframe_time", table_name="ohlcv_candles"
    )
    op.drop_table("ohlcv_candles")
    op.drop_index(
        op.f("ix_monthly_target_history_monthly_target_id"),
        table_name="monthly_target_history",
    )
    op.drop_table("monthly_target_history")
    op.drop_table("trading_sessions")
    op.drop_index(
        "ix_option_chain_snapshots_underlying_captured",
        table_name="option_chain_snapshots",
    )
    op.drop_table("option_chain_snapshots")
    op.drop_table("monthly_targets")
    op.drop_index(
        "uq_market_instruments_future_contract",
        table_name="market_instruments",
        postgresql_where=sa.text("instrument_type = 'FUTURE'"),
    )
    op.drop_index(
        "uq_market_instruments_contract",
        table_name="market_instruments",
        postgresql_where=sa.text("instrument_type = 'OPTION'"),
    )
    op.drop_index(
        "ix_market_instruments_underlying_expiry",
        table_name="market_instruments",
        postgresql_where=sa.text("active"),
    )
    op.drop_table("market_instruments")
    op.drop_table("india_vix")
    op.drop_table("daily_performance")
    # ### end Alembic commands ###
