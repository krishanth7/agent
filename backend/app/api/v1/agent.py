"""Agent routes.

Read-only, and deliberately so. There is no endpoint to start, stop, arm or
configure the agent, because there is no agent — and because the control
surface for one should not be designed before the risk engine that must be
able to veto it.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.dependencies import AgentServiceDep
from app.schemas.agent import AgentStatusResponse

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get(
    "/status",
    response_model=AgentStatusResponse,
    summary="Trading agent state and capability flags",
)
async def read_agent_status(service: AgentServiceDep) -> AgentStatusResponse:
    """Report that trading is disabled and nothing is connected."""
    return await service.get_status()
