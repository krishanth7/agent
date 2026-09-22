"""Agent status API schema."""

from __future__ import annotations

from app.domain.enums import AgentState
from app.schemas.common import ApiModel


class AgentStatusResponse(ApiModel):
    """What the trading agent is currently doing.

    In this phase the answer is always "nothing". The boolean capability flags
    are stated explicitly rather than implied, because an operator must be able
    to confirm at a glance that no order path is live. A dashboard that stays
    silent about whether trading is armed is a dashboard that will eventually
    mislead someone.
    """

    state: AgentState
    mode: str
    live_trading_enabled: bool
    paper_trading_enabled: bool
    broker_connected: bool
    market_data_connected: bool
