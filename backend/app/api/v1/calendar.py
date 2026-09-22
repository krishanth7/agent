"""Calendar routes.

Kept in its own module because the calendar is a distinct read model: it serves
a whole month of compact markers in one request, rather than the full derived
breakdown that the daily endpoints return.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.dependencies import PerformanceServiceDep
from app.schemas.performance import PerformanceCalendarResponse

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get(
    "/calendar",
    response_model=PerformanceCalendarResponse,
    summary="Recorded sessions for a month",
)
async def read_calendar(
    service: PerformanceServiceDep,
    year: int = Query(ge=1970, le=2200, description="Four-digit year."),
    month: int = Query(ge=1, le=12, description="Month number, 1-12."),
) -> PerformanceCalendarResponse:
    """Return every recorded session in the requested month.

    Dates with no journal entry are omitted rather than returned as zeroes, so
    the client can distinguish "no session recorded" from "traded to flat".

    This payload intentionally carries enough information for the calendar to
    render every cell *and* for a client to resolve a date selection without a
    follow-up request.
    """
    return await service.get_calendar(year=year, month=month)
