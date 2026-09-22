"""Account routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.dependencies import AccountServiceDep
from app.schemas.account import AccountSummaryResponse

router = APIRouter(prefix="/account", tags=["account"])


@router.get(
    "/summary",
    response_model=AccountSummaryResponse,
    summary="Trading account funds snapshot",
)
async def read_account_summary(service: AccountServiceDep) -> AccountSummaryResponse:
    """Return available balance, used margin and total capital.

    Read-only. There is no counterpart write endpoint: this figure is owned by
    the broker, and a later phase will source it from a funds API. The `source`
    field states the provenance so a client can never present mock capital as
    a real balance.
    """
    return await service.get_summary()
