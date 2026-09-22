"""Performance endpoint tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def test_today(client: AsyncClient, api: str) -> None:
    response = await client.get(f"{api}/performance/today")

    assert response.status_code == 200
    assert response.json() == {
        "date": "2026-09-22",
        "realized_pnl": 420.00,
        "daily_target": 333,
        "remaining_to_target": 0.00,
        "progress_percentage": 126.13,
        "status": "achieved",
        "trades": 3,
        "wins": 2,
        "losses": 1,
        "win_rate": 66.67,
        "currency": "INR",
        "source": "mock",
    }


async def test_today_progress_is_not_capped_at_one_hundred(
    client: AsyncClient, api: str
) -> None:
    payload = (await client.get(f"{api}/performance/today")).json()
    assert payload["progress_percentage"] > 100


async def test_monthly(client: AsyncClient, api: str) -> None:
    response = await client.get(f"{api}/performance/monthly")

    assert response.status_code == 200
    payload = response.json()
    assert payload["year"] == 2026
    assert payload["month"] == 9
    assert payload["realized_pnl"] == 4280.00
    assert payload["monthly_target"] == 10000.00
    assert payload["remaining_to_target"] == 5720.00
    assert payload["progress_percentage"] == 42.80
    assert payload["currency"] == "INR"


async def test_monthly_totals_match_the_journal(client: AsyncClient, api: str) -> None:
    """Aggregates must be derived, never hard-coded."""
    monthly = (await client.get(f"{api}/performance/monthly")).json()
    calendar = (
        await client.get(
            f"{api}/performance/calendar", params={"year": 2026, "month": 9}
        )
    ).json()

    assert monthly["realized_pnl"] == sum(
        day["realized_pnl"] for day in calendar["days"]
    )
    assert monthly["trades"] == sum(day["trades"] for day in calendar["days"])
    assert monthly["wins"] == sum(day["wins"] for day in calendar["days"])
    # 07 Sep is a recorded no-trade day, so it is not an active session.
    assert monthly["active_sessions"] == len(calendar["days"]) - 1


async def test_monthly_accepts_explicit_period(client: AsyncClient, api: str) -> None:
    payload = (
        await client.get(
            f"{api}/performance/monthly", params={"year": 2026, "month": 8}
        )
    ).json()

    assert payload["month"] == 8
    assert payload["realized_pnl"] == 0
    assert payload["trades"] == 0


@pytest.mark.parametrize(
    "params",
    [
        {"month": 13},
        {"month": 0},
        {"month": -1},
        {"year": 1800},
        {"month": "september"},
    ],
)
async def test_monthly_rejects_invalid_periods(
    client: AsyncClient, api: str, params: dict[str, str | int]
) -> None:
    response = await client.get(f"{api}/performance/monthly", params=params)
    assert response.status_code == 422


class TestDateSpecificPerformance:
    async def test_known_date(self, client: AsyncClient, api: str) -> None:
        response = await client.get(f"{api}/performance/2026-09-22")

        assert response.status_code == 200
        payload = response.json()
        assert payload["date"] == "2026-09-22"
        assert payload["realized_pnl"] == 420.00
        assert payload["status"] == "achieved"
        assert payload["win_rate"] == 66.67

    async def test_loss_session(self, client: AsyncClient, api: str) -> None:
        payload = (await client.get(f"{api}/performance/2026-09-16")).json()

        assert payload["realized_pnl"] == -310.00
        assert payload["status"] == "loss"
        # Remaining is measured from the current P&L: 333 - (-310).
        assert payload["remaining_to_target"] == 643.00

    async def test_in_progress_session(self, client: AsyncClient, api: str) -> None:
        payload = (await client.get(f"{api}/performance/2026-09-15")).json()

        assert payload["realized_pnl"] == 95.00
        assert payload["status"] == "in_progress"
        assert payload["remaining_to_target"] == 238.00

    async def test_recorded_no_trade_day(self, client: AsyncClient, api: str) -> None:
        payload = (await client.get(f"{api}/performance/2026-09-07")).json()

        assert payload["status"] == "not_started"
        assert payload["trades"] == 0
        assert payload["win_rate"] == 0

    async def test_unknown_date_returns_404(
        self, client: AsyncClient, api: str
    ) -> None:
        """Documented policy: a specific missing record is a miss, not a zero."""
        response = await client.get(f"{api}/performance/2026-09-05")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PERFORMANCE_RECORD_NOT_FOUND"

    @pytest.mark.parametrize(
        "value", ["not-a-date", "2026-13-01", "2026-09-31", "22-09-2026", "2026-02-30"]
    )
    async def test_invalid_date_returns_422(
        self, client: AsyncClient, api: str, value: str
    ) -> None:
        response = await client.get(f"{api}/performance/{value}")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_slash_separated_date_is_not_a_route(
        self, client: AsyncClient, api: str
    ) -> None:
        """`2026/09/22` adds path segments, so it never reaches the handler.

        404 rather than 422 is correct here: there is no such route to
        validate against.
        """
        response = await client.get(f"{api}/performance/2026/09/22")
        assert response.status_code == 404
