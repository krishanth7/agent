"""Monthly profit target and its change history."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import CURRENCY
from app.db.base import Base, Money, TimestampMixin, enum_check, uuid_pk
from app.domain.enums import CalculationMode, TargetChangeSource


class MonthlyTarget(Base, TimestampMixin):
    """The user's self-defined goal for one calendar month.

    A goal, explicitly — not projected, expected or guaranteed income.

    SINGLE-ACCOUNT ASSUMPTION
    -------------------------
    `(year, month)` is unique, which encodes that this deployment serves
    exactly one trading account. There is no authentication and no account
    table, so adding an `account_id` now would be a foreign key to nothing.
    When multi-account support arrives, this constraint becomes
    `(account_id, year, month)` and the migration is mechanical.
    """

    __tablename__ = "monthly_targets"

    id: Mapped[uuid.UUID] = uuid_pk()

    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    month: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    target_amount: Mapped[Money] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default=CURRENCY)

    #: How the daily target was derived from this monthly figure. Stored rather
    #: than assumed, so a target set under a 30-day split stays interpretable
    #: after the rule changes to remaining NSE sessions.
    calculation_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default=CalculationMode.CALENDAR_DAYS_30.value
    )

    history: Mapped[list[MonthlyTargetHistory]] = relationship(
        back_populates="monthly_target",
        # No cascade delete. Deleting a target must not erase the record of
        # what it used to be; the FK is RESTRICT, so the database refuses.
        passive_deletes=False,
    )

    __table_args__ = (
        UniqueConstraint("year", "month", name="uq_monthly_targets_year_month"),
        CheckConstraint("month BETWEEN 1 AND 12", name="month"),
        # A defensive bound, not a trading limit. The service validates the
        # same rule; the database enforces it for every other writer —
        # migrations, seeds, and a future CLI that has no Pydantic layer.
        CheckConstraint("target_amount > 0", name="amount_positive"),
        CheckConstraint(
            enum_check("calculation_mode", CalculationMode),
            name="calculation_mode",
        ),
    )


class MonthlyTargetHistory(Base):
    """An append-only record of every target change.

    Exists so "why was the daily target ₹500 that week?" remains answerable
    after the target moves. Financial evidence is never silently overwritten:
    the current value lives on `monthly_targets`, and each edit appends here.

    There is no `updated_at` because a history row is never updated.
    """

    __tablename__ = "monthly_target_history"

    id: Mapped[uuid.UUID] = uuid_pk()

    monthly_target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monthly_targets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    #: Null on the very first entry, where there is no prior value.
    previous_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 4), nullable=True
    )
    new_amount: Mapped[Money] = mapped_column(nullable=False)

    changed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    monthly_target: Mapped[MonthlyTarget] = relationship(back_populates="history")

    __table_args__ = (
        CheckConstraint("new_amount > 0", name="new_amount_positive"),
        CheckConstraint(
            enum_check("source", TargetChangeSource),
            name="source",
        ),
    )
