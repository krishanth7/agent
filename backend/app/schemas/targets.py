"""Monthly/daily target API schemas."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import MAX_MONTHLY_TARGET
from app.domain.enums import CalculationMode
from app.schemas.common import ApiModel, CurrencyMixin, NonNegativeMoney


class MonthlyTargetResponse(ApiModel, CurrencyMixin):
    """A monthly goal and the daily goal derived from it.

    This is a user-defined *target*, not projected, expected or guaranteed
    income. `calculation_mode` is on the wire so a client can tell how the
    daily figure was derived without assuming the rule.
    """

    monthly_target: NonNegativeMoney
    daily_target: int = Field(ge=0)
    calculation_mode: CalculationMode


class UpdateMonthlyTargetRequest(BaseModel):
    """Request body for setting a new monthly goal."""

    model_config = ConfigDict(extra="forbid")

    #: `allow_inf_nan=False` is load-bearing. Python's `json` module accepts
    #: the non-standard `NaN` and `Infinity` literals, so a client can put one
    #: on the wire; without this, `Infinity` would sail past a `gt=0` check.
    #:
    #: The upper bound is a sanity guard against malformed input, not a
    #: trading limit — it sits far above any plausible retail goal.
    monthly_target: Annotated[
        Decimal,
        Field(gt=0, le=MAX_MONTHLY_TARGET, allow_inf_nan=False),
    ]
