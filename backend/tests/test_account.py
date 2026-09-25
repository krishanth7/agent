"""Account endpoint tests."""

from __future__ import annotations

import json

from app.main import create_app
from httpx import ASGITransport, AsyncClient

from tests.brokers.conftest import broker_settings


async def test_account_summary(client: AsyncClient, api: str) -> None:
    response = await client.get(f"{api}/account/summary")

    assert response.status_code == 200
    assert response.json() == {
        "available_balance": 25000.00,
        "used_margin": 0.00,
        "total_capital": 25000.00,
        "currency": "INR",
        "source": "mock",
    }


async def test_money_is_a_json_number_not_a_string(
    client: AsyncClient, api: str
) -> None:
    """The frontend consumes these directly; no parse step should be needed."""
    payload = (await client.get(f"{api}/account/summary")).json()

    for field in ("available_balance", "used_margin", "total_capital"):
        assert isinstance(payload[field], (int, float)), field
        assert not isinstance(payload[field], str), field


async def test_money_has_no_floating_point_artifacts(
    client: AsyncClient, api: str
) -> None:
    """Guards the Decimal pipeline.

    Values are quantized to paise before encoding, so the serialized form must
    be exact — never `25000.000000000004`.
    """
    raw = (await client.get(f"{api}/account/summary")).text
    document = json.loads(raw)

    assert document["available_balance"] == 25000
    assert document["total_capital"] == 25000
    assert document["used_margin"] == 0
    # No long mantissa anywhere in the serialized body.
    assert "0000000" not in raw


async def test_source_is_declared(client: AsyncClient, api: str) -> None:
    """Mock capital must never be presentable as a real balance."""
    payload = (await client.get(f"{api}/account/summary")).json()
    assert payload["source"] == "mock"


async def test_source_stays_mock_even_when_a_broker_is_configured() -> None:
    """A connectable broker must not make an invented figure look real.

    This is the failure mode Phase 3 newly makes possible. Credentials are now
    present and the integration is enabled, so a reader — or a dashboard — could
    reasonably assume the balance below came from Angel One. It did not: there is
    no broker-backed account repository, `get_account_repository` returns the
    mock unconditionally, and 25000.00 is a literal in a module.

    The assertion is that `source` keeps saying so. If a later phase wires the
    funds call through without also wiring provenance, this fails rather than
    silently relabelling demonstration data as a settled account balance.
    """
    app = create_app(broker_settings())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = (await client.get("/api/v1/account/summary")).json()

    assert payload["source"] == "mock"
    assert payload["total_capital"] == 25000.00


async def test_balance_is_read_only(client: AsyncClient, api: str) -> None:
    """There is no write path for the account balance, by design."""
    response = await client.put(
        f"{api}/account/summary", json={"available_balance": 1_000_000}
    )
    assert response.status_code == 405
