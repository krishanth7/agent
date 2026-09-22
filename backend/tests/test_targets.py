"""Monthly target endpoint tests."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient


async def test_get_default_monthly_target(client: AsyncClient, api: str) -> None:
    response = await client.get(f"{api}/targets/monthly")

    assert response.status_code == 200
    assert response.json() == {
        "monthly_target": 10000.00,
        "daily_target": 333,
        "calculation_mode": "calendar_days_30",
        "currency": "INR",
    }


@pytest.mark.parametrize(
    ("monthly", "expected_daily"),
    [(10000, 333), (10010, 334), (15000, 500), (20000, 667)],
)
async def test_put_recalculates_daily_target(
    client: AsyncClient, api: str, monthly: int, expected_daily: int
) -> None:
    response = await client.put(
        f"{api}/targets/monthly", json={"monthly_target": monthly}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["monthly_target"] == monthly
    assert payload["daily_target"] == expected_daily


async def test_put_persists_for_subsequent_reads(client: AsyncClient, api: str) -> None:
    await client.put(f"{api}/targets/monthly", json={"monthly_target": 15000})

    payload = (await client.get(f"{api}/targets/monthly")).json()
    assert payload["monthly_target"] == 15000
    assert payload["daily_target"] == 500


async def test_put_propagates_to_performance_endpoints(
    client: AsyncClient, api: str
) -> None:
    """The target is authoritative; derived figures must follow it."""
    await client.put(f"{api}/targets/monthly", json={"monthly_target": 30000})

    today = (await client.get(f"{api}/performance/today")).json()
    assert today["daily_target"] == 1000
    # ₹420 against a ₹1,000 bar is no longer an achievement.
    assert today["status"] == "in_progress"
    assert today["remaining_to_target"] == 580


@pytest.mark.parametrize(
    "body",
    [
        {"monthly_target": 0},
        {"monthly_target": -1},
        {"monthly_target": -5000},
        {"monthly_target": "abc"},
        {"monthly_target": None},
        {"monthly_target": 1e12},  # above the sanity bound
        {},  # missing field
        {"monthly_target": 10000, "unexpected": True},  # extra="forbid"
    ],
)
async def test_put_rejects_invalid_targets(
    client: AsyncClient, api: str, body: dict[str, Any]
) -> None:
    response = await client.put(f"{api}/targets/monthly", json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
async def test_put_rejects_non_finite_numbers(
    client: AsyncClient, api: str, literal: str
) -> None:
    """Python's json module accepts these non-standard literals.

    Without `allow_inf_nan=False`, `Infinity` would pass a `gt=0` check.
    """
    response = await client.put(
        f"{api}/targets/monthly",
        content=f'{{"monthly_target": {literal}}}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422


async def test_put_rejects_malformed_json(client: AsyncClient, api: str) -> None:
    response = await client.put(
        f"{api}/targets/monthly",
        content='{"monthly_target": ',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422


async def test_rejected_target_does_not_mutate_state(
    client: AsyncClient, api: str
) -> None:
    await client.put(f"{api}/targets/monthly", json={"monthly_target": -5000})

    payload = (await client.get(f"{api}/targets/monthly")).json()
    assert payload["monthly_target"] == 10000


async def test_error_body_does_not_echo_submitted_value(
    client: AsyncClient, api: str
) -> None:
    """Validation errors must not reflect arbitrary client input back."""
    response = await client.put(
        f"{api}/targets/monthly", json={"monthly_target": "<script>alert(1)</script>"}
    )

    assert response.status_code == 422
    assert "<script>" not in response.text
