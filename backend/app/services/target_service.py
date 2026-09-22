"""Monthly/daily target application service."""

from __future__ import annotations

from decimal import Decimal

from app.core.constants import MAX_MONTHLY_TARGET
from app.core.exceptions import InvalidMonthlyTargetError
from app.domain.calculations import calculate_daily_target, quantize_money
from app.domain.enums import CalculationMode
from app.repositories.interfaces.target_repository import TargetRepository
from app.schemas.targets import MonthlyTargetResponse


class TargetService:
    """Owns the monthly goal and the rule that splits it into a daily goal."""

    def __init__(self, repository: TargetRepository) -> None:
        self._repository = repository

    async def get_monthly_target(self) -> MonthlyTargetResponse:
        target = await self._repository.get_monthly_target()
        return self._to_response(target.amount)

    async def set_monthly_target(self, amount: Decimal) -> MonthlyTargetResponse:
        """Validate and store a new goal.

        The schema already enforces these bounds, so reaching a raise here
        means the service was called from somewhere other than the HTTP layer.
        Re-checking is cheap and keeps the service safe to reuse from a future
        CLI, scheduled job or test harness that has no Pydantic layer in front
        of it.
        """
        if not amount.is_finite() or amount <= 0:
            raise InvalidMonthlyTargetError("Monthly target must be greater than zero.")
        if amount > MAX_MONTHLY_TARGET:
            raise InvalidMonthlyTargetError(
                f"Monthly target must not exceed {MAX_MONTHLY_TARGET:f}."
            )

        stored = await self._repository.set_monthly_target(quantize_money(amount))
        return self._to_response(stored.amount)

    @staticmethod
    def _to_response(amount: Decimal) -> MonthlyTargetResponse:
        return MonthlyTargetResponse(
            monthly_target=quantize_money(amount),
            daily_target=calculate_daily_target(amount),
            calculation_mode=CalculationMode.CALENDAR_DAYS_30,
        )
