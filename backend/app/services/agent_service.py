"""Agent status service.

There is no agent. This service exists so the API can state that fact
explicitly and consistently, rather than leaving a client to infer it from the
absence of endpoints.
"""

from __future__ import annotations

from typing import Final

from app.domain.enums import AgentState
from app.schemas.agent import AgentStatusResponse

#: Short machine-readable description of what this deployment is for.
_MODE: Final = "frontend_backend_foundation"


class AgentService:
    """Reports a hard-coded disabled state.

    The values below are constants, not configuration. Making them settable
    would create a path where a misconfigured environment variable could
    advertise live trading on a system that has no broker, no risk engine and
    no execution validation. That flag should only ever become `True` in a
    phase that has all three.
    """

    async def get_status(self) -> AgentStatusResponse:
        return AgentStatusResponse(
            state=AgentState.DISABLED,
            mode=_MODE,
            live_trading_enabled=False,
            paper_trading_enabled=False,
            broker_connected=False,
            market_data_connected=False,
        )
