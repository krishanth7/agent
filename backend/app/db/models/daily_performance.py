"""Realized outcome of one trading session."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Money, TimestampMixin, enum_check, uuid_pk
from app.domain.enums import DataSource


class DailyPerformance(Base, TimestampMixin):
    """One row per trading date: what actually happened that session.

    STORED FACTS ONLY
    -----------------
    Win rate, progress percentage, remaining-to-target and the achieved/loss
    status are all absent by design. Every one of them is a pure function of
    the columns below plus the prevailing target, and `domain.calculations`
    already owns those rules. Persisting them would create a second source of
    truth that goes stale the moment a user edits their monthly target — which
    the dashboard lets them do at any time.

    `daily_target` is the exception: it records the goal *in force when the
    session was recorded*, which is history rather than a derivation, and is
    not recoverable from today's target.
    """

    __tablename__ = "daily_performance"

    id: Mapped[uuid.UUID] = uuid_pk()

    #: The exchange-local trading date. A `DATE`, not a timestamp: a session
    #: belongs to a calendar day in IST, and storing an instant would invite
    #: timezone arithmetic every time the calendar renders.
    trading_date: Mapped[dt.date] = mapped_column(Date, nullable=False)

    realized_pnl: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0"))
    #: Mark-to-market on positions still open at the close. Null means "not
    #: computed", which is different from zero.
    unrealized_pnl: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 4), nullable=True
    )
    #: Brokerage plus statutory charges. Non-negative; a rebate would be
    #: modelled as a separate adjustment rather than a negative fee.
    fees: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0"))
    #: Realized P&L after fees. Stored rather than derived because the exact
    #: relationship between gross and net will gain terms (STT, stamp duty,
    #: GST) that this schema does not yet itemise.
    net_pnl: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0"))

    #: The daily goal in force on this date. See the class docstring.
    daily_target: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0"))

    trade_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    win_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    loss_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Trades that closed flat. Counted separately so `wins + losses` is not
    #: forced to equal `trades`.
    breakeven_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    source: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        # Single-account assumption, identical to `monthly_targets`. Becomes
        # `(account_id, trading_date)` when accounts exist.
        UniqueConstraint("trading_date", name="uq_daily_performance_trading_date"),
        CheckConstraint("trade_count >= 0", name="trade_count"),
        CheckConstraint("win_count >= 0", name="win_count"),
        CheckConstraint("loss_count >= 0", name="loss_count"),
        CheckConstraint("breakeven_count >= 0", name="breakeven_count"),
        CheckConstraint("fees >= 0", name="fees_non_negative"),
        # Outcomes cannot outnumber attempts. This catches a whole class of
        # ingestion bug — double-counting a fill, or attributing one trade to
        # both the win and the loss bucket.
        CheckConstraint(
            "win_count + loss_count + breakeven_count <= trade_count",
            name="outcomes_within_trades",
        ),
        CheckConstraint(enum_check("source", DataSource), name="source"),
    )
