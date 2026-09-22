"""Agent status tests.

These assert that the system reports itself as inert. They are safety tests,
not feature tests: if any of them ever start failing, something has enabled a
trading capability that this phase has no risk machinery to control.
"""

from __future__ import annotations

from httpx import AsyncClient


async def test_agent_status(client: AsyncClient, api: str) -> None:
    response = await client.get(f"{api}/agent/status")

    assert response.status_code == 200
    assert response.json() == {
        "state": "disabled",
        "mode": "frontend_backend_foundation",
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "broker_connected": False,
        "market_data_connected": False,
    }


async def test_every_trading_capability_is_off(client: AsyncClient, api: str) -> None:
    payload = (await client.get(f"{api}/agent/status")).json()

    assert payload["state"] == "disabled"
    assert not any(
        payload[flag]
        for flag in (
            "live_trading_enabled",
            "paper_trading_enabled",
            "broker_connected",
            "market_data_connected",
        )
    )


async def test_agent_state_is_not_writable(client: AsyncClient, api: str) -> None:
    """No control surface exists for the agent."""
    response = await client.put(f"{api}/agent/status", json={"state": "live_trading"})
    assert response.status_code == 405
