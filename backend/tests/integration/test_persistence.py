"""§60 — the monthly target must survive a restart.

This is the requirement that separates Phase 3 from Phase 2. Under the mock
backend the target lived in a process-local singleton, so "persistence" meant
"until you press Ctrl-C". The scenario below is the one written into the
specification: set ₹15,000, observe ₹500/day, restart, and find both unchanged.

WHAT "RESTART" MEANS HERE
-------------------------
A genuinely separate Python process, spawned with `subprocess`. That matters.
Rebuilding the app object inside this interpreter would leave the module-level
engine, the settings singleton and any repository state intact — so a target
cached in memory would sail through such a test and still be lost the moment
the service actually restarted. The only thing the child shares with the parent
is the database itself, which is precisely the claim under test.
"""

from __future__ import annotations

import json
import os

# Used once, with a fixed argument list and no shell. The "restart" this
# module tests is a real second interpreter, which is the whole point.
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Final

import pytest
from httpx import AsyncClient

_BACKEND_ROOT: Final = Path(__file__).resolve().parents[2]

#: Runs in a fresh interpreter: new engine, new pool, new settings singleton,
#: new repository instance. Reads through the same repository the API uses, so
#: this exercises the production read path rather than a hand-written SELECT.
_READBACK_PROGRAM: Final = """
import asyncio, json
from app.db.session import session_scope, dispose_engine
from app.repositories.postgres.target_repository import PostgresTargetRepository

async def main():
    try:
        async with session_scope() as session:
            target = await PostgresTargetRepository(session).get_monthly_target()
        print(json.dumps({"monthly_target": str(target.amount)}))
    finally:
        await dispose_engine()

asyncio.run(main())
"""


def _read_target_in_a_new_process() -> Decimal:
    """The monthly target as a brand-new interpreter sees it."""
    result = subprocess.run(  # noqa: S603  (fixed argv, no shell, no user input)
        [sys.executable, "-c", _READBACK_PROGRAM],
        cwd=_BACKEND_ROOT,
        env=dict(os.environ),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"read-back process failed:\n{result.stdout}\n{result.stderr}")

    # The last line, because the child also configures logging and may emit a
    # startup line before its result.
    payload: dict[str, str] = json.loads(result.stdout.strip().splitlines()[-1])
    return Decimal(payload["monthly_target"])


async def test_monthly_target_survives_a_restart(client: AsyncClient) -> None:
    """The §60 scenario, end to end."""
    response = await client.put(
        "/api/v1/targets/monthly", json={"monthly_target": 15000}
    )

    assert response.status_code == 200
    assert response.json()["monthly_target"] == 15000
    assert response.json()["daily_target"] == 500

    # --- restart ---------------------------------------------------------
    # Compared as `Decimal`, not as the transported string: the column is
    # `NUMERIC(20, 4)`, so the value comes back as "15000.0000". That trailing
    # scale is the column doing its job, and pinning the test to the literal
    # text would make a harmless precision change look like data loss.
    assert _read_target_in_a_new_process() == Decimal("15000")

    # And the API, asked again, still derives the same daily figure.
    after = (await client.get("/api/v1/targets/monthly")).json()
    assert after["monthly_target"] == 15000
    assert after["daily_target"] == 500


async def test_performance_reports_database_provenance(client: AsyncClient) -> None:
    """Figures read from PostgreSQL must not be labelled `mock`.

    `source` is the one field whose entire job is to stop invented data being
    read as real. It was wrong once — the repositories were returning rows from
    PostgreSQL under `source: mock`, because the response mixin defaulted that
    way and nothing overrode it — so it is asserted explicitly.
    """
    payload = (await client.get("/api/v1/performance/today")).json()

    assert payload["source"] == "database"


async def test_account_stays_mock_even_with_a_database(client: AsyncClient) -> None:
    """§42: there is no broker, so there is no real balance to persist.

    A figure in a database reads as authoritative in a way that a literal in a
    mock module does not. Until a broker actually reports funds, the account
    endpoint must keep saying so — having a database available is not a reason
    to start implying ₹25,000 is a settled fact.
    """
    payload = (await client.get("/api/v1/account/summary")).json()

    assert payload["source"] == "mock"
