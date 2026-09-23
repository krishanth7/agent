"""Normalized instrument master."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, enum_check, uuid_pk
from app.domain.enums import DataSource, InstrumentType, OptionType


class MarketInstrument(Base, TimestampMixin):
    """Anything that can be quoted or traded, in normalized form.

    NEVER PARSE THE SYMBOL
    ----------------------
    A broker symbol like `NIFTY26SEP25000CE` encodes underlying, expiry,
    strike and right in a format that varies by broker and changes without
    notice. Every one of those is a real, typed, indexed column here. The
    symbol is retained as an identifier for talking to a venue — it is not the
    place to look up what a contract *is*.

    That is also why `(underlying, expiry, strike_price, option_type,
    exchange)` carries a uniqueness guarantee of its own: a contract's identity
    is its economic terms, not its display name.
    """

    __tablename__ = "market_instruments"

    id: Mapped[uuid.UUID] = uuid_pk()

    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Venue segment, e.g. `NFO` for NSE derivatives, `NSE` for cash.
    segment: Mapped[str] = mapped_column(String(16), nullable=False)
    #: The venue's tradable symbol. Opaque by policy — see the class docstring.
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Root the contract derives from, e.g. `NIFTY`. Equal to `symbol` for an
    #: index row, which keeps "all instruments on NIFTY" a single predicate.
    underlying: Mapped[str] = mapped_column(String(32), nullable=False)

    instrument_type: Mapped[str] = mapped_column(String(16), nullable=False)

    #: Numeric identifier used by broker market-data feeds. Nullable because
    #: no broker is connected; it is populated by instrument-master sync.
    exchange_token: Mapped[str | None] = mapped_column(String(32), nullable=True)

    #: Contract multiplier. Null for an index, which is not tradable.
    lot_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Minimum price increment.
    tick_size: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)

    #: Null for an index or a cash instrument; required for futures and
    #: options, which the table constraints enforce.
    expiry: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    strike_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    option_type: Mapped[str | None] = mapped_column(String(2), nullable=True)

    #: Whether the contract is currently tradable. Expired contracts stay in
    #: the table — their historical candles must remain attributable.
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    source: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "exchange", "symbol", name="uq_market_instruments_exchange_symbol"
        ),
        CheckConstraint(
            enum_check("instrument_type", InstrumentType),
            name="instrument_type",
        ),
        CheckConstraint(enum_check("source", DataSource), name="source"),
        CheckConstraint(
            f"option_type IS NULL OR {enum_check('option_type', OptionType)}",
            name="option_type",
        ),
        # Shape rules per instrument type. These stop a half-populated option
        # row — the kind an instrument-master sync produces when a vendor
        # changes a column — from entering the table at all.
        CheckConstraint(
            "(instrument_type <> 'OPTION') OR "
            "(expiry IS NOT NULL AND strike_price IS NOT NULL "
            "AND option_type IS NOT NULL)",
            name="option_fields_complete",
        ),
        CheckConstraint(
            "(instrument_type <> 'FUTURE') OR "
            "(expiry IS NOT NULL AND strike_price IS NULL AND option_type IS NULL)",
            name="future_fields_complete",
        ),
        CheckConstraint(
            "(instrument_type <> 'INDEX') OR "
            "(expiry IS NULL AND strike_price IS NULL AND option_type IS NULL)",
            name="index_fields_empty",
        ),
        CheckConstraint(
            "strike_price IS NULL OR strike_price > 0",
            name="strike_positive",
        ),
        CheckConstraint(
            "lot_size IS NULL OR lot_size > 0",
            name="lot_size_positive",
        ),
        # Economic identity of a derivative contract, independent of symbology.
        # A partial index rather than a table constraint because NULLs in a
        # plain UNIQUE are never equal to each other, which would let unlimited
        # duplicate INDEX rows through the same constraint.
        Index(
            "uq_market_instruments_contract",
            "exchange",
            "underlying",
            "expiry",
            "strike_price",
            "option_type",
            unique=True,
            postgresql_where=text("instrument_type = 'OPTION'"),
        ),
        Index(
            "uq_market_instruments_future_contract",
            "exchange",
            "underlying",
            "expiry",
            unique=True,
            postgresql_where=text("instrument_type = 'FUTURE'"),
        ),
        # Serves the option-chain lookup: every contract on one underlying for
        # one expiry, which is the access pattern for building a chain.
        Index(
            "ix_market_instruments_underlying_expiry",
            "underlying",
            "expiry",
            postgresql_where=text("active"),
        ),
    )
