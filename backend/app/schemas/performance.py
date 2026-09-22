"""Performance API schemas."""

from __future__ import annotations

from datetime import date

from pydantic import Field

from app.domain.enums import DailyTargetStatus
from app.schemas.common import (
    ApiModel,
    CurrencyMixin,
    Money,
    NonNegativeMoney,
    Percentage,
    SourcedMixin,
)


class DailyPerformanceResponse(ApiModel, CurrencyMixin, SourcedMixin):
    """One session's realized outcome measured against its daily target.

    `progress_percentage` is intentionally uncapped: beating the target is
    information worth reporting. Clamping belongs to the progress bar, not to
    the number.
    """

    date: date
    realized_pnl: Money
    daily_target: int = Field(ge=0)
    remaining_to_target: NonNegativeMoney
    progress_percentage: Percentage
    status: DailyTargetStatus
    trades: int = Field(ge=0)
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    win_rate: Percentage


class MonthlyPerformanceResponse(ApiModel, CurrencyMixin, SourcedMixin):
    """Month-to-date realized performance against the monthly goal."""

    year: int = Field(ge=1970, le=2200)
    month: int = Field(ge=1, le=12)
    realized_pnl: Money
    monthly_target: NonNegativeMoney
    remaining_to_target: NonNegativeMoney
    progress_percentage: Percentage
    trades: int = Field(ge=0)
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    active_sessions: int = Field(ge=0)


class CalendarDayResponse(ApiModel):
    """A single recorded session as the calendar consumes it.

    Leaner than `DailyPerformanceResponse` on purpose: the calendar renders a
    grid of markers and needs the status plus the P&L, not the full derived
    breakdown. Keeping this payload small is what lets the whole month load in
    one request instead of one request per cell.
    """

    date: date
    realized_pnl: Money
    trades: int = Field(ge=0)
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    daily_target: int = Field(ge=0)
    status: DailyTargetStatus


class PerformanceCalendarResponse(ApiModel, CurrencyMixin, SourcedMixin):
    """A month of recorded sessions.

    Only dates with a journal entry appear in `days`. A missing date means no
    session was recorded — the calendar renders that as a blank cell rather
    than a zero, because "no data" and "traded to flat" are different facts.
    """

    year: int = Field(ge=1970, le=2200)
    month: int = Field(ge=1, le=12)
    days: list[CalendarDayResponse]
