"""Database liveness probing for the health endpoints.

WHAT A CLIENT IS TOLD
---------------------
A category and a latency. Never a host, port, username, database name, driver
message or connection string. A health endpoint is typically the least
protected route in a system, and a failure message like
`connection to server at "10.0.3.14", port 5432 failed: FATAL: password
authentication failed for user "trading_agent"` hands an attacker the topology
and a valid username in one line.

The full exception is logged server-side, where the operator can see it and the
internet cannot.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import get_logger
from app.db.session import get_engine

logger = get_logger(__name__)

DatabaseState = Literal["up", "down", "not_configured"]

#: Failure categories reported to clients. Coarse on purpose — see module docs.
_TIMEOUT: Literal["timeout"] = "timeout"
_UNAVAILABLE: Literal["unavailable"] = "unavailable"


@dataclass(frozen=True, slots=True)
class DatabaseStatus:
    """Outcome of one liveness probe."""

    state: DatabaseState
    #: Round-trip time of the probe query. `None` when it never completed.
    latency_ms: float | None = None
    #: Failure category, or `None` when healthy. Never a driver message.
    error: str | None = None

    @property
    def is_healthy(self) -> bool:
        """Whether this state should count as ready to serve.

        `not_configured` is healthy: the mock backend genuinely has no database
        to be unready about, and reporting it as a failure would make every
        database-free run look broken.
        """
        return self.state != "down"


async def check_database(timeout: float) -> DatabaseStatus:  # noqa: ASYNC109
    """Round-trip a trivial query against PostgreSQL.

    `SELECT 1` rather than a table read: the probe must answer "is the database
    reachable and accepting queries?", not "is the schema what I expect?".
    Mixing the two means a pending migration reports as an outage.

    A timeout is mandatory, not optional. Without one, a database that accepts
    a TCP connection but never answers — a failing-over primary, an exhausted
    connection pool, a network black hole — would hang the health endpoint,
    which is precisely when an orchestrator most needs a prompt answer.

    ON THE SUPPRESSED LINT
    ----------------------
    ASYNC109 says an async function should not take a `timeout` parameter, and
    that callers should wrap the call in `asyncio.timeout` instead. That advice
    is right for a function whose timeout means "give up and raise" — the
    caller owns the cancellation scope, and a parameter only reimplements it
    badly.

    It is wrong here, because this function does not propagate a timeout: it
    *converts* one into a reported state. "The database did not answer within
    the budget" is one of the outcomes this probe exists to describe, and it
    has to be caught inside to be turned into `DatabaseStatus(state="down",
    error="timeout")`. Pushing the bound out to the caller would make every
    caller catch `TimeoutError` and construct that status itself, which is the
    duplication this function exists to prevent. The suppression is narrow —
    one line — and `asyncio.timeout` is still what does the work below.
    """
    started = time.perf_counter()
    try:
        async with asyncio.timeout(timeout):
            engine = get_engine()
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except TimeoutError:
        logger.warning("database_health_timeout timeout_s=%s", timeout)
        return DatabaseStatus(state="down", error=_TIMEOUT)
    except (SQLAlchemyError, OSError) as exc:
        # `OSError` is not redundant. A refused TCP connection surfaces as a
        # bare `ConnectionRefusedError` from the event loop's socket layer,
        # before asyncpg has a DBAPI error to wrap and before SQLAlchemy can
        # translate it into `OperationalError`. Catching only `SQLAlchemyError`
        # let that escape as an unhandled 500 — verified against a stopped
        # container, which is the single most likely way this probe is
        # exercised in anger.
        #
        # Logged in full server-side; the client gets only the category.
        logger.warning("database_health_failed error=%s", exc, exc_info=True)
        return DatabaseStatus(state="down", error=_UNAVAILABLE)

    elapsed_ms = (time.perf_counter() - started) * 1000
    return DatabaseStatus(state="up", latency_ms=round(elapsed_ms, 2))
