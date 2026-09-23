"""Option-chain snapshots and per-strike quotes.

WHY TWO TABLES
--------------
A chain capture is one logical event — "the NIFTY 24-Sep-2026 chain, as at
09:20:00, from this provider, with spot at 25,013.40" — that yields a few
hundred strike rows. Repeating the spot price and capture identity on every
strike would both waste space and, far worse, allow those copies to disagree.
`option_chain_snapshots` holds the event; `option_quotes` holds the strikes.

POINT-IN-TIME RECONSTRUCTION
----------------------------
Future model training must be able to answer "what did the agent actually know
at 09:20:00?" without leaking information from later bars. That requires the
snapshot instant, the underlying price *at that instant*, and provenance, all
stored alongside the quotes. Every one of those is a column here, and none of
them is nullable on the snapshot.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Price, enum_check, uuid_pk
from app.domain.enums import DataSource, OptionType


class OptionChainSnapshot(Base):
    """Identity of one option-chain capture.

    NO INGESTION EXISTS. Empty until Phase 4.
    """

    __tablename__ = "option_chain_snapshots"

    id: Mapped[uuid.UUID] = uuid_pk()

    #: The instant the chain was observed.
    captured_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    underlying: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Spot level of the underlying at capture time. Non-nullable: a chain
    #: without its spot cannot be used to compute moneyness, and moneyness is
    #: the axis nearly every option feature is expressed against.
    spot_price: Mapped[Price] = mapped_column(nullable=False)
    expiry: Mapped[dt.date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # Idempotency: re-running an ingestion for the same instant, chain and
        # provider must collide rather than silently create a second snapshot.
        UniqueConstraint(
            "underlying",
            "expiry",
            "captured_at",
            "source",
            name="uq_option_chain_snapshots_identity",
        ),
        CheckConstraint(enum_check("source", DataSource), name="source"),
        CheckConstraint("spot_price > 0", name="spot_positive"),
        Index(
            "ix_option_chain_snapshots_underlying_captured",
            "underlying",
            "captured_at",
        ),
    )


class OptionQuote(Base):
    """One strike's state within a chain snapshot.

    Becomes a TimescaleDB hypertable on `timestamp`. This is by far the
    highest-volume table in the schema: a single weekly NIFTY expiry carries
    well over a hundred strikes across both rights, and capturing every minute
    of a session produces roughly 100k rows per expiry per day.

    Greeks and implied volatility are columns, not computations. Phase 3
    calculates none of them — the schema simply has to be able to retain what
    Phase 4 ingests and what a later pricing layer derives.
    """

    __tablename__ = "option_quotes"

    #: Observation instant. Duplicated from the parent snapshot because
    #: TimescaleDB partitions on a column of this table, and a hypertable
    #: cannot partition on a joined value.
    timestamp: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("market_instruments.id", ondelete="RESTRICT"),
        primary_key=True,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(32), primary_key=True, nullable=False)

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        # RESTRICT, not CASCADE: deleting a snapshot header must not take a
        # few hundred observations with it.
        ForeignKey("option_chain_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )

    #: Denormalized from `market_instruments` so the overwhelmingly common
    #: filters — one expiry, a strike band, one right — are answerable without
    #: joining a second table on every chain query.
    strike_price: Mapped[Price] = mapped_column(nullable=False)
    option_type: Mapped[str] = mapped_column(String(2), nullable=False)
    expiry: Mapped[dt.date] = mapped_column(Date, nullable=False)

    last_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    bid_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    ask_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    bid_quantity: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ask_quantity: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    open_interest: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Signed: open interest can fall. Not a simple non-negative count.
    change_in_open_interest: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )

    #: Decimal fraction, e.g. 0.1425 for 14.25%.
    implied_volatility: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    delta: Mapped[Decimal | None] = mapped_column(Numeric(16, 8), nullable=True)
    gamma: Mapped[Decimal | None] = mapped_column(Numeric(16, 8), nullable=True)
    theta: Mapped[Decimal | None] = mapped_column(Numeric(16, 8), nullable=True)
    vega: Mapped[Decimal | None] = mapped_column(Numeric(16, 8), nullable=True)
    rho: Mapped[Decimal | None] = mapped_column(Numeric(16, 8), nullable=True)

    #: Underlying level at this instant, carried per row so a quote remains
    #: self-describing even when read without its snapshot.
    underlying_price: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 4), nullable=True
    )

    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(enum_check("source", DataSource), name="source"),
        CheckConstraint(enum_check("option_type", OptionType), name="option_type"),
        CheckConstraint("strike_price > 0", name="strike_positive"),
        # Prices may be zero — a far out-of-the-money option genuinely trades
        # at 0.05 and can be quoted at 0 — but never negative.
        CheckConstraint(
            "last_price IS NULL OR last_price >= 0",
            name="last_price_non_negative",
        ),
        CheckConstraint(
            "bid_price IS NULL OR bid_price >= 0",
            name="bid_non_negative",
        ),
        CheckConstraint(
            "ask_price IS NULL OR ask_price >= 0",
            name="ask_non_negative",
        ),
        CheckConstraint("volume IS NULL OR volume >= 0", name="volume_non_negative"),
        CheckConstraint(
            "open_interest IS NULL OR open_interest >= 0",
            name="open_interest_non_negative",
        ),
        CheckConstraint(
            "implied_volatility IS NULL OR implied_volatility >= 0",
            name="iv_non_negative",
        ),
        # Delta is bounded by definition; a value outside [-1, 1] means the
        # pricing input was wrong, and it should not reach a feature set.
        CheckConstraint(
            "delta IS NULL OR (delta >= -1 AND delta <= 1)",
            name="delta_bounded",
        ),
        # Serves "the chain for this expiry across a time window", which is
        # both the UI query and the feature-generation query. `timestamp`
        # leads because Timescale prunes chunks on it first.
        Index(
            "ix_option_quotes_expiry_time_strike",
            "expiry",
            "timestamp",
            "strike_price",
            "option_type",
        ),
        # Serves "the full history of one contract", used when reconstructing
        # what a position was worth through its life. The primary key leads
        # with `timestamp` (Timescale partitions on it), so it cannot answer
        # an instrument-first lookup efficiently on its own.
        Index(
            "ix_option_quotes_instrument_time",
            "instrument_id",
            text('"timestamp" DESC'),
        ),
        # Supports fetching every strike of a captured chain, and lets the
        # RESTRICT foreign key check its dependents without a sequential scan.
        Index("ix_option_quotes_snapshot", "snapshot_id"),
    )
