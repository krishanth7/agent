"""Order, execution, position, trade and journal schema.

SCHEMA ONLY — NOTHING WRITES TO THESE TABLES
--------------------------------------------
No order endpoint exists. No broker adapter exists. No strategy, signal or
risk engine exists. Every table in this module is created empty by the initial
migration and stays empty for the whole of Phase 3. They are defined now so
that the execution phase writes a migration for *behaviour*, not for a schema
it should have designed up front.

WHY ORDERS, EXECUTIONS, POSITIONS AND TRADES ARE FOUR TABLES
------------------------------------------------------------
A single `trades` row cannot honestly represent broker reality. One order
frequently fills in several parts, at several prices, across several
milliseconds; a position accumulates across orders; and "a trade" — the thing
a human reasons about as one idea — may span several of each. Collapsing that
into one row means reconstructing average entry price from data that was never
stored, which is precisely the kind of quiet inaccuracy that makes a P&L
disagree with the broker's own statement.

BROKER NEUTRALITY
-----------------
There is no `zerodha_orders` or `angel_one_positions`. The venue is a `broker`
column and its identifier a `broker_order_id`, so a second broker is rows, not
tables.

IMMUTABILITY
------------
Financial history is append-oriented. Every foreign key below is RESTRICT:
deleting an instrument cannot erase the orders that referenced it, and
deleting an order cannot erase the fills that prove what happened.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Money, Price, TimestampMixin, enum_check, uuid_pk
from app.domain.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    PositionStatus,
)


class Order(Base, TimestampMixin):
    """An instruction to a broker. SCHEMA ONLY — never created by this phase."""

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = uuid_pk()

    #: Which venue this was sent to. Null until an order is actually routed.
    broker: Mapped[str | None] = mapped_column(String(32), nullable=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Our own idempotency key, generated before submission. This is what makes
    #: a retry after a network timeout safe: the broker rejects the duplicate
    #: rather than the account acquiring a second unintended position.
    client_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("market_instruments.id", ondelete="RESTRICT"), nullable=False
    )

    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(24), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Null for a market order.
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    trigger_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)

    status: Mapped[str] = mapped_column(String(24), nullable=False)

    #: Which strategy asked for this, and which revision of it. Never a bare
    #: `is_automated` flag: reproducing a decision requires knowing the exact
    #: logic version that produced it.
    strategy_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strategy_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Correlates back to the signal that motivated the order.
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=True
    )

    submitted_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    filled_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: The broker's untouched response. Genuinely semi-structured — every
    #: broker returns a different shape — and retained verbatim so a dispute
    #: can be settled against what the venue actually said. Searchable facts
    #: are real columns above; this is evidence, not an index.
    broker_raw_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, nullable=True
    )

    __table_args__ = (
        CheckConstraint(enum_check("side", OrderSide), name="side"),
        CheckConstraint(enum_check("order_type", OrderType), name="order_type"),
        CheckConstraint(enum_check("status", OrderStatus), name="status"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("price IS NULL OR price >= 0", name="price_non_negative"),
        # One broker identifier maps to one order. Partial, because the column
        # is null for every order that has not been routed, and NULLs would
        # otherwise not collide.
        Index(
            "uq_orders_broker_order_id",
            "broker",
            "broker_order_id",
            unique=True,
            postgresql_where=text("broker_order_id IS NOT NULL"),
        ),
        Index("ix_orders_instrument_created", "instrument_id", "created_at"),
        Index("ix_orders_status", "status"),
    )


class Execution(Base):
    """One fill against an order. SCHEMA ONLY — never created by this phase.

    Append-only: a fill is an event that happened, so there is no `updated_at`
    and nothing revises it.
    """

    __tablename__ = "executions"

    id: Mapped[uuid.UUID] = uuid_pk()

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    #: The venue's identifier for this fill. Unique per broker, and the key
    #: that makes replaying a fills feed idempotent.
    broker_execution_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Price] = mapped_column(nullable=False)
    fees: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0"))

    executed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("price >= 0", name="price_non_negative"),
        CheckConstraint("fees >= 0", name="fees_non_negative"),
        UniqueConstraint(
            "order_id",
            "broker_execution_id",
            name="uq_executions_order_broker_execution",
        ),
        Index("ix_executions_order", "order_id"),
        Index("ix_executions_executed_at", "executed_at"),
    )


class Position(Base, TimestampMixin):
    """Net exposure in one instrument. SCHEMA ONLY — nothing maintains this."""

    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = uuid_pk()

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("market_instruments.id", ondelete="RESTRICT"), nullable=False
    )

    #: Signed: negative is short. Zero is legitimate for a closed position
    #: that is being retained for its history.
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    average_entry_price: Mapped[Price] = mapped_column(nullable=False)
    realized_pnl: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0"))
    unrealized_pnl: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 4), nullable=True
    )

    status: Mapped[str] = mapped_column(String(16), nullable=False)

    opened_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(enum_check("status", PositionStatus), name="status"),
        CheckConstraint("average_entry_price >= 0", name="avg_price_non_negative"),
        # A closed position must record when it closed, and an open one must
        # not claim to have closed.
        CheckConstraint(
            "(status = 'closed' AND closed_at IS NOT NULL) OR "
            "(status <> 'closed' AND closed_at IS NULL)",
            name="closed_at_matches_status",
        ),
        # At most one open position per instrument. Partial, so the table can
        # retain any number of historical closed positions for the same
        # contract.
        Index(
            "uq_positions_open_instrument",
            "instrument_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index("ix_positions_status", "status"),
    )


class Trade(Base, TimestampMixin):
    """A completed round trip. SCHEMA ONLY — nothing creates this.

    Derived from orders and executions rather than being their substitute: this
    is the human-legible unit that the journal annotates.
    """

    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = uuid_pk()

    #: The order that opened the trade. Nullable because a trade may later be
    #: reconstructed from a fills feed with no local order row.
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("market_instruments.id", ondelete="RESTRICT"), nullable=False
    )

    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    entry_price: Mapped[Price] = mapped_column(nullable=False)
    #: Null while the trade is still open.
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)

    gross_pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    fees: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0"))
    net_pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)

    opened_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    closed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exit_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    strategy_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strategy_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        CheckConstraint(enum_check("side", OrderSide), name="side"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("entry_price >= 0", name="entry_price_non_negative"),
        CheckConstraint("fees >= 0", name="fees_non_negative"),
        CheckConstraint(
            "closed_at IS NULL OR closed_at >= opened_at",
            name="closed_after_opened",
        ),
        Index("ix_trades_instrument_opened", "instrument_id", "opened_at"),
        Index("ix_trades_opened_at", "opened_at"),
    )


class TradeJournal(Base):
    """Post-hoc analysis of one trade. SCHEMA ONLY — nothing classifies here.

    NO AUTOMATIC DIAGNOSIS. Phase 3 writes nothing to this table and infers
    nothing. Every analytical column is nullable precisely so that a future
    diagnostic layer can fill them in progressively, and so that an
    unclassified trade is representable rather than being forced into a
    misleading default category.

    `diagnostic_category` is intentionally a free-ish string rather than a
    CHECK-constrained vocabulary: the loss taxonomy (direction error, regime
    error, late entry, false breakout, volatility shock, IV crush, theta decay,
    poor strike selection, bad risk/reward, excessive spread, slippage, data
    quality, execution error, normal statistical loss) will be refined by
    what the data actually shows, and pinning it now would mean a migration
    every time that understanding improves.
    """

    __tablename__ = "trade_journal"

    id: Mapped[uuid.UUID] = uuid_pk()

    trade_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trades.id", ondelete="RESTRICT"), nullable=False
    )

    market_regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    signal_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Model confidence at entry, 0..1.
    signal_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 4), nullable=True
    )

    entry_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnostic_category: Mapped[str | None] = mapped_column(String(48), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Unstructured supporting detail — indicator values, regime scores — whose
    #: shape will change as the diagnostic layer evolves.
    diagnostics: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "signal_confidence IS NULL OR "
            "(signal_confidence >= 0 AND signal_confidence <= 1)",
            name="confidence_bounded",
        ),
        UniqueConstraint("trade_id", name="uq_trade_journal_trade_id"),
    )
