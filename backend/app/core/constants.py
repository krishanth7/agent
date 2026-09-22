"""Domain-wide constants.

Values that appear in more than one module live here so a business rule is
never expressed as a bare literal at two different call sites.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final
from zoneinfo import ZoneInfo

#: All trading-domain timestamps are resolved in exchange-local time. NSE runs
#: on IST and never observes daylight saving, but using a named zone rather
#: than a fixed +05:30 offset keeps the intent explicit.
IST: Final = ZoneInfo("Asia/Kolkata")

#: The only currency this system deals in.
CURRENCY: Final = "INR"

#: Denominator for splitting a monthly goal into a daily goal.
#:
#: PHASE 3 NOTE: this fixed 30-day denominator mirrors the Phase 1 frontend
#: rule. A market-calendar implementation should eventually replace it with the
#: actual number of remaining NSE trading sessions, if the product
#: specification adopts trading-day-based targets. Only this constant and
#: `calculate_daily_target` need to change.
ASSUMED_DAYS_PER_MONTH: Final = 30

#: Smallest representable money unit (one paisa). Every monetary value crossing
#: a service boundary is quantized to this so no sub-paisa residue survives.
MONEY_QUANTUM: Final = Decimal("0.01")

#: Upper bound for a user-defined monthly target: ₹10 crore.
#:
#: This is a sanity bound against malformed or adversarial input, not a trading
#: limit. It sits far above any plausible goal for a retail options account
#: while still rejecting values that would overflow display formatting.
MAX_MONTHLY_TARGET: Final = Decimal("100000000")

#: NSE equity and F&O session, used for display and for the weekend rule.
SESSION_OPEN: Final = "09:15"
SESSION_CLOSE: Final = "15:30"
