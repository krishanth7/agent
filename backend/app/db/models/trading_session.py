"""Application trading day."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, Date, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, enum_check, uuid_pk
from app.domain.enums import TradingSessionStatus


class TradingSession(Base, TimestampMixin):
    """One market day as the application sees it.

    NOT a broker login or an authentication session. This records that the
    application considered a given date a trading day, when it began watching
    and when it stopped.

    No NSE holiday calendar is ingested in this phase, so nothing assigns
    `HOLIDAY` automatically — the status exists so that the Phase 4 exchange
    calendar has somewhere to write, not because it is populated today.
    """

    __tablename__ = "trading_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()

    trading_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    #: Exchange identifier, e.g. `NSE`. Present from the start so a second
    #: venue does not require a schema change.
    market: Mapped[str] = mapped_column(String(16), nullable=False, default="NSE")

    #: Instants, not clock times: `TIMESTAMPTZ` so the actual moment the
    #: session opened survives a server moving between regions.
    started_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    status: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "trading_date", "market", name="uq_trading_sessions_trading_date_market"
        ),
        CheckConstraint(
            enum_check("status", TradingSessionStatus),
            name="status",
        ),
        # A session cannot end before it begins. Null-tolerant: the comparison
        # yields NULL (treated as satisfied) while either end is unknown.
        CheckConstraint(
            "ended_at IS NULL OR started_at IS NULL OR ended_at >= started_at",
            name="end_after_start",
        ),
    )
