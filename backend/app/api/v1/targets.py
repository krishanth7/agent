"""Target routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.dependencies import TargetServiceDep
from app.schemas.targets import MonthlyTargetResponse, UpdateMonthlyTargetRequest

router = APIRouter(prefix="/targets", tags=["targets"])


@router.get(
    "/monthly",
    response_model=MonthlyTargetResponse,
    summary="Current monthly and derived daily target",
)
async def read_monthly_target(service: TargetServiceDep) -> MonthlyTargetResponse:
    return await service.get_monthly_target()


@router.put(
    "/monthly",
    response_model=MonthlyTargetResponse,
    summary="Set the monthly target",
)
async def update_monthly_target(
    payload: UpdateMonthlyTargetRequest,
    service: TargetServiceDep,
) -> MonthlyTargetResponse:
    """Store a new monthly goal and return it with the recalculated daily goal.

    The daily figure is derived server-side and returned in the same response,
    so a client never has to reimplement the rounding rule to stay consistent
    with the backend.
    """
    return await service.set_monthly_target(payload.monthly_target)
