"""Performance routes.

ROUTE ORDERING: the literal paths below are declared before the
``/{session_date}`` catch-all. Starlette matches in declaration order, so
moving the parameterised route above them would make ``/performance/today``
resolve as a date and fail validation. The calendar route lives in
`calendar.py` and is included ahead of this router for the same reason.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Path, Query

from app.dependencies import PerformanceServiceDep
from app.schemas.common import ErrorResponse
from app.schemas.performance import DailyPerformanceResponse, MonthlyPerformanceResponse

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get(
    "/today",
    response_model=DailyPerformanceResponse,
    summary="Today's session against the daily target",
)
async def read_today(service: PerformanceServiceDep) -> DailyPerformanceResponse:
    """Return the current session's realized performance.

    Always returns a record. A trading day with nothing booked yet reports a
    zero P&L and `not_started` status, because the dashboard must always have
    something coherent to render for today.
    """
    return await service.get_today()


@router.get(
    "/monthly",
    response_model=MonthlyPerformanceResponse,
    summary="Month-to-date performance against the monthly target",
)
async def read_monthly(
    service: PerformanceServiceDep,
    year: int | None = Query(default=None, ge=1970, le=2200),
    month: int | None = Query(default=None, ge=1, le=12),
) -> MonthlyPerformanceResponse:
    """Aggregate a month's sessions against the monthly goal.

    Defaults to the current reporting month when year/month are omitted.
    """
    return await service.get_monthly(year=year, month=month)


@router.get(
    "/{session_date}",
    response_model=DailyPerformanceResponse,
    summary="A specific session's performance",
    responses={
        404: {"model": ErrorResponse, "description": "No record for that date."}
    },
)
async def read_for_date(
    service: PerformanceServiceDep,
    session_date: date = Path(description="ISO date, e.g. 2026-09-22."),
) -> DailyPerformanceResponse:
    """Return one historical session.

    Responds 404 when no session was recorded for the date. A malformed date
    is rejected as 422 by path validation before this handler runs.
    """
    return await service.get_for_date(session_date)
