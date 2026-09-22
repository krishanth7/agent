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
    """Provenance of a payload.

    Surfaced on responses so the frontend can visibly distinguish demo figures
    from real ones. This matters enormously the day a broker is connected: a
    number must never be able to masquerade as live account data.
    """

    MOCK = "mock"
    DATABASE = "database"
    BROKER = "broker"
    SIMULATION = "simulation"


class CalculationMode(StrEnum):
    """How a daily target was derived from a monthly target."""

    CALENDAR_DAYS_30 = "calendar_days_30"
    #: Reserved for the market-calendar work in a later phase.
    NSE_TRADING_SESSIONS = "nse_trading_sessions"
