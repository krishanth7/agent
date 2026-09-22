"""Pure business rules for targets and performance.

Every function here is synchronous and side-effect free: given the same inputs
it always returns the same output, touching no I/O, clock or configuration.
That is what makes the rules cheap to test exhaustively, and it is why the API
layer must never re-derive any of them inline.

All monetary arithmetic uses `Decimal`. Binary floating point cannot represent
`0.1` exactly, and a financial figure that drifts by a paisa per operation is a
defect that compounds silently.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.core.constants import ASSUMED_DAYS_PER_MONTH, MONEY_QUANTUM
from app.domain.enums import DailyTargetStatus

_PERCENT_QUANTUM = Decimal("0.01")
_WHOLE = Decimal("1")


def quantize_money(value: Decimal) -> Decimal:
    """Round a monetary value to whole paise, half away from zero.

    Banker's rounding (Python's `Decimal` default) would round 2.5 to 2, which
    is defensible statistically but surprising on a financial statement. Money
    in this system always rounds half up.
    """
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def calculate_daily_target(monthly_target: Decimal) -> int:
    """Split a monthly goal into a whole-rupee daily goal.

    Rounding is explicitly ROUND_HALF_UP rather than `Decimal`'s default
    ROUND_HALF_EVEN, so this matches the Phase 1 frontend rule exactly:
    ``₹10,000 → ₹333`` and ``₹10,010 → ₹334``.

    Non-positive targets yield 0 rather than raising: a zero goal is a
    meaningful "no target set" state, and the status rules treat a ₹0 bar as
    cleared by any profit.

    PHASE 3 NOTE: the fixed 30-day denominator should eventually be replaced
    with the actual count of remaining NSE trading sessions if the product
    adopts trading-day-based targets. That requires the exchange holiday
    calendar, which is deliberately out of scope here.
    """
    if monthly_target <= 0:
        return 0

    daily = monthly_target / Decimal(ASSUMED_DAYS_PER_MONTH)
    return int(daily.quantize(_WHOLE, rounding=ROUND_HALF_UP))


def get_daily_target_status(
    realized_pnl: Decimal,
    daily_target: Decimal,
) -> DailyTargetStatus:
    """Classify a session against its daily target.

    The ordering matters: a loss is reported as a loss even when the target is
    zero, and a flat session reads as "not started" rather than "achieved"
    against a ₹0 bar.
    """
    if realized_pnl < 0:
        return DailyTargetStatus.LOSS
    if realized_pnl == 0:
        return DailyTargetStatus.NOT_STARTED

    target = max(daily_target, Decimal(0))
    if realized_pnl >= target:
        return DailyTargetStatus.ACHIEVED
    return DailyTargetStatus.IN_PROGRESS


def calculate_remaining_to_target(
    realized_pnl: Decimal,
    daily_target: Decimal,
) -> Decimal:
    """Improvement still required to reach the target, floored at zero.

    Semantics: ``max(target - realized_pnl, 0)``. This is measured from the
    *current* P&L, so a session sitting at -₹120 against a ₹333 target reports
    ₹453 — the amount of ground that must actually be made up, not the ₹333
    that would be required from flat. The floor at zero means a beaten target
    reports ₹0 rather than a negative "surplus"; surplus is already legible
    from the progress percentage exceeding 100%.
    """
    if daily_target <= 0:
        return Decimal("0.00")
    return quantize_money(max(daily_target - realized_pnl, Decimal(0)))


def calculate_progress_percentage(value: Decimal, target: Decimal) -> Decimal:
    """Completion against a target, as an uncapped percentage.

    Deliberately not clamped to 100: beating a target is information the API
    should report faithfully. Presentation layers may cap their progress-bar
    geometry, but the number itself stays honest.
    """
    if target <= 0:
        return Decimal("0.00")
    percentage = (value / target) * Decimal(100)
    return percentage.quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def calculate_win_rate(wins: int, trades: int) -> Decimal:
    """Winning share of trades, as a percentage.

    Returns 0 for a session with no trades rather than dividing by zero. Note
    that this is wins over *trades*, not wins over wins-plus-losses, which
    leaves room for a future breakeven outcome that is neither.
    """
    if trades <= 0:
        return Decimal("0.00")
    rate = (Decimal(wins) / Decimal(trades)) * Decimal(100)
    return rate.quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_UP)
