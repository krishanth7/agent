"""Calendar endpoint tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def test_calendar_returns_the_month(client: AsyncClient, api: str) -> None:
    response = await client.get(
        f"{api}/performance/calendar", params={"year": 2026, "month": 9}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["year"] == 2026
    assert payload["month"] == 9
    assert payload["source"] == "mock"
    assert len(payload["days"]) == 16


async def test_days_are_chronological(client: AsyncClient, api: str) -> None:
    payload = (
        await client.get(
            f"{api}/performance/calendar", params={"year": 2026, "month": 9}
        )
    ).json()

    dates = [day["date"] for day in payload["days"]]
    assert dates == sorted(dates)


async def test_calendar_covers_every_status(client: AsyncClient, api: str) -> None:
    """The demo month must exercise each state the UI can render."""
    payload = (
        await client.get(
            f"{api}/performance/calendar", params={"year": 2026, "month": 9}
        )
    ).json()

    statuses = {day["status"] for day in payload["days"]}
    assert statuses == {"achieved", "in_progress", "loss", "not_started"}


async def test_calendar_omits_weekends(client: AsyncClient, api: str) -> None:
    """NSE is closed Saturday and Sunday, so no session can exist then."""
    from datetime import date

    payload = (
        await client.get(
            f"{api}/performance/calendar", params={"year": 2026, "month": 9}
        )
    ).json()

    for day in payload["days"]:
        weekday = date.fromisoformat(day["date"]).weekday()
        assert weekday < 5, day["date"]


async def test_empty_month_returns_empty_list(client: AsyncClient, api: str) -> None:
    """An absent month is an empty result, not a 404."""
    payload = (
        await client.get(
            f"{api}/performance/calendar", params={"year": 2026, "month": 1}
        )
    ).json()

    assert payload["days"] == []


async def test_calendar_status_follows_the_current_target(
    client: AsyncClient, api: str
) -> None:
    await client.put(f"{api}/targets/monthly", json={"monthly_target": 30000})

    payload = (
        await client.get(
            f"{api}/performance/calendar", params={"year": 2026, "month": 9}
        )
    ).json()
    day = next(d for d in payload["days"] if d["date"] == "2026-09-22")

    assert day["daily_target"] == 1000
    assert day["status"] == "in_progress"


@pytest.mark.parametrize(
    "params",
    [
        {"year": 2026},
        {"month": 9},
        {},
        {"year": 2026, "month": 13},
        {"year": "x", "month": 9},
    ],
)
async def test_rejects_invalid_parameters(
    client: AsyncClient, api: str, params: dict[str, str | int]
) -> None:
    response = await client.get(f"{api}/performance/calendar", params=params)
    assert response.status_code == 422
