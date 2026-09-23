"""Closed vocabularies for the trading domain.

Anything the API emits as a fixed set of strings is defined here, so a status
is never a bare literal scattered across services, schemas and tests.
"""

from __future__ import annotations

from enum import StrEnum


class DailyTargetStatus(StrEnum):
    """A session's standing against its daily target."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    ACHIEVED = "achieved"
    LOSS = "loss"


class AgentState(StrEnum):
    """Lifecycle states the trading agent may occupy.

    The full vocabulary is declared now so that future phases extend behaviour
    rather than the contract. Phase 2 only ever reports `DISABLED` — no
    transitions are implemented, because there is no agent to transition.
    """

    DISABLED = "disabled"
    INITIALIZING = "initializing"
    OBSERVING = "observing"
    PAPER_TRADING = "paper_trading"
    LIVE_TRADING = "live_trading"
    PAUSED = "paused"
    ERROR = "error"
    EMERGENCY_STOP = "emergency_stop"


class DataSource(StrEnum):
    """Provenance of a payload or a stored row.

    Surfaced on responses so the frontend can visibly distinguish demo figures
    from real ones. This matters enormously the day a broker is connected: a
    number must never be able to masquerade as live account data.

    Also persisted on every market-data row. A dataset that cannot say where an
    observation came from cannot be audited, and a model trained on it cannot
    be reproduced — so `source` is non-nullable wherever prices are stored.
    Never label a row `NSE` unless it genuinely arrived from the exchange.
    """

    MOCK = "mock"
    DATABASE = "database"
    BROKER = "broker"
    SIMULATION = "simulation"
    #: Written by `python -m app.db.seed`. Deterministic, invented, and clearly
    #: not market data.
    DEVELOPMENT_SEED = "development_seed"
    #: Reserved for genuine exchange-sourced data in Phase 4.
    NSE = "nse"


class InstrumentType(StrEnum):
    """What kind of tradable thing a `market_instruments` row describes."""

    INDEX = "INDEX"
    FUTURE = "FUTURE"
    OPTION = "OPTION"


class OptionType(StrEnum):
    """Exchange notation for an option's right."""

    CALL = "CE"
    PUT = "PE"


class Timeframe(StrEnum):
    """Candle aggregation intervals.

    Declared as a closed set so a typo cannot silently create a parallel
    series: `"5min"` and `"5m"` would otherwise be two different instruments'
    worth of data under one symbol.
    """

    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    D1 = "1d"


class TradingSessionStatus(StrEnum):
    """Lifecycle of one application trading day.

    Note this is the *market* day, not a broker login. No NSE holiday calendar
    is ingested yet, so `HOLIDAY` exists in the vocabulary but nothing assigns
    it automatically.
    """

    SCHEDULED = "scheduled"
    OPEN = "open"
    CLOSED = "closed"
    HOLIDAY = "holiday"
    DISABLED = "disabled"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    STOP_LOSS_MARKET = "stop_loss_market"


class OrderStatus(StrEnum):
    """Order lifecycle.

    SCHEMA ONLY. No code transitions an order between these states, because no
    order can be created: this service exposes no order endpoint and no broker
    adapter exists. The vocabulary is declared now so the Phase 5 execution
    work extends behaviour rather than the schema.
    """

    PENDING = "pending"
    SUBMITTED = "submitted"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PositionStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class TargetChangeSource(StrEnum):
    """Who or what changed a monthly target."""

    USER = "user"
    DEVELOPMENT_SEED = "development_seed"


class CalculationMode(StrEnum):
    """How a daily target was derived from a monthly target."""

    CALENDAR_DAYS_30 = "calendar_days_30"
    #: Reserved for the market-calendar work in a later phase.
    NSE_TRADING_SESSIONS = "nse_trading_sessions"
