"""Time-series market data: OHLCV candles and India VIX.

HYPERTABLE NOTE
---------------
Both tables below become TimescaleDB hypertables in the initial migration.
A hypertable's unique indexes must include the partitioning column, which is
why `timestamp` appears in every primary key here. See `docs/database.md` for
the chunk-interval reasoning.

APPEND-ORIENTED
---------------
Neither table carries `updated_at`. A candle is an observation of a moment in
the past; it is not edited. Corrections arrive as a re-ingest under the same
key, which the primary key turns into an explicit upsert rather than a silent
duplicate.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Price, Quantity, enum_check
from app.domain.enums import DataSource, Timeframe


class OhlcvCandle(Base):
    """One aggregated price bar for one instrument at one timeframe.

    Covers the index, futures and individual option contracts alike. There is
    deliberately no `nifty_spot_ohlcv` or `nifty_futures_ohlcv`: the
    instrument dimension is already normalized in `market_instruments`, and
    per-underlying tables would multiply the schema for no query benefit.

    NO INGESTION EXISTS. Nothing in this phase connects to a feed, a broker or
    an exchange. The only writer is `python -m app.db.seed`, whose rows carry
    `source = development_seed` — invented daily bars, present so the
    hypertable is exercised rather than merely created. Real ingestion, and
    the first row that may legitimately claim `source = nse`, arrive in
    Phase 4.
    """

    __tablename__ = "ohlcv_candles"

    #: Bar open time, in UTC. The exchange-local rendering is presentation.
    timestamp: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        # RESTRICT: deleting an instrument must never silently erase its price
        # history. Retiring a contract is `active = false`, not a DELETE.
        ForeignKey("market_instruments.id", ondelete="RESTRICT"),
        primary_key=True,
        nullable=False,
    )
    timeframe: Mapped[str] = mapped_column(String(8), primary_key=True, nullable=False)
    #: Part of the key so the same bar from two providers can coexist and be
    #: compared, rather than one silently overwriting the other.
    source: Mapped[str] = mapped_column(String(32), primary_key=True, nullable=False)

    open: Mapped[Price] = mapped_column(nullable=False)
    high: Mapped[Price] = mapped_column(nullable=False)
    low: Mapped[Price] = mapped_column(nullable=False)
    close: Mapped[Price] = mapped_column(nullable=False)

    volume: Mapped[Quantity] = mapped_column(nullable=False, default=0)
    #: Null for a cash/index bar, where open interest is not a concept.
    open_interest: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(enum_check("timeframe", Timeframe), name="timeframe"),
        CheckConstraint(enum_check("source", DataSource), name="source"),
        # OHLC coherence, enforced at the storage layer rather than trusted
        # from the feed. A bar whose high is below its close is corrupt, and
        # silently training a model on it is worse than rejecting the write.
        CheckConstraint(
            "high >= low AND high >= open AND high >= close "
            "AND low <= open AND low <= close",
            name="ohlc_coherent",
        ),
        CheckConstraint("volume >= 0", name="volume_non_negative"),
        CheckConstraint(
            "open_interest IS NULL OR open_interest >= 0",
            name="open_interest_non_negative",
        ),
        CheckConstraint(
            "open > 0 AND high > 0 AND low > 0 AND close > 0",
            name="prices_positive",
        ),
        # THE query this table exists to serve: one instrument, one timeframe,
        # newest-first over a time range. DESC matches the scan direction of
        # "most recent N bars", which is what both charting and feature
        # generation ask for.
        Index(
            "ix_ohlcv_candles_instrument_timeframe_time",
            "instrument_id",
            "timeframe",
            # `timestamp` is a type name in SQL, so it is quoted explicitly.
            # A raw expression is needed for DESC ordering; it is a static
            # literal, with no interpolation of any kind.
            text('"timestamp" DESC'),
        ),
    )


class IndiaVix(Base):
    """India VIX, the NSE volatility index.

    Modelled as its own small table rather than as a row in
    `market_instruments` + `ohlcv_candles`, because VIX is not tradable and
    has no volume, open interest, lot size or expiry. Forcing it through the
    instrument model would mean a permanently half-null instrument row.

    NO INGESTION EXISTS. As with `ohlcv_candles`, the only writer in this phase
    is the development seed, and its rows are labelled `development_seed`.
    """

    __tablename__ = "india_vix"

    timestamp: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(32), primary_key=True, nullable=False)

    open: Mapped[Price] = mapped_column(nullable=False)
    high: Mapped[Price] = mapped_column(nullable=False)
    low: Mapped[Price] = mapped_column(nullable=False)
    close: Mapped[Price] = mapped_column(nullable=False)

    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(enum_check("source", DataSource), name="source"),
        CheckConstraint(
            "high >= low AND high >= open AND high >= close "
            "AND low <= open AND low <= close",
            name="ohlc_coherent",
        ),
        CheckConstraint(
            "open > 0 AND high > 0 AND low > 0 AND close > 0",
            name="prices_positive",
        ),
    )
