"""Internal domain records.

These are what repositories return and services operate on. They are kept
separate from the Pydantic API schemas so the wire contract can evolve (field
renames, versioned payloads, camelCase transforms) without dragging the
business rules along with it.

Frozen dataclasses rather than Pydantic models: no validation or serialization
is needed here, and immutability makes accidental mutation of repository state
impossible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.enums import DataSource


@dataclass(frozen=True, slots=True)
class AccountSummaryData:
    """A broker account's funds snapshot."""

    available_balance: Decimal
    used_margin: Decimal
    total_capital: Decimal
    source: DataSource


@dataclass(frozen=True, slots=True)
class MonthlyTargetData:
    """The user's self-defined monthly goal.

    A goal, explicitly — not projected, expected or guaranteed income.
    """

    amount: Decimal


@dataclass(frozen=True, slots=True)
class DailySessionData:
    """One trading session's realized outcome.

    `trades` counts attempts; `wins` and `losses` need not sum to it, leaving
    room for breakeven outcomes in a later phase.
    """

    session_date: date
    realized_pnl: Decimal
    trades: int
    wins: int
    losses: int


@dataclass(frozen=True, slots=True)
class PerformanceTotals:
    """Aggregate across a set of sessions."""

    realized_pnl: Decimal
    trades: int
    wins: int
    losses: int
    active_sessions: int
