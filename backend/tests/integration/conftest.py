"""Fixtures for the tests that need a real database.

WHY A SEPARATE DATABASE
-----------------------
Every test here creates and destroys `trading_agent_test`, never the
development database. A suite that truncates the database a developer is
looking at is a suite people stop running, and "the tests wiped my seed data"
is not a defensible trade for a slightly simpler fixture.

WHY THE SCHEMA COMES FROM ALEMBIC
---------------------------------
The schema is built by running the real migrations, not by
`Base.metadata.create_all`. `create_all` would test the models against
themselves and prove nothing about the migration — which is the artefact that
actually runs in production, and the one that carries the TimescaleDB
hypertable conversions and the CHECK constraints. If a migration is broken,
these tests must fail.

WHY A SKIP RATHER THAN A FAILURE
--------------------------------
No database reachable means the suite is skipped, loudly, with the reason
attached. A hard failure would make `pytest` red on a machine where Docker is
not running, which trains people to ignore red. A silent pass would be worse:
it would report success for tests that never executed. CI, where the database
is always present, sees no skips.
"""

from __future__ import annotations

import asyncio
import os

# Used once, with a fixed argument list and no shell. See `_run_migrations`.
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Final

import pytest
import pytest_asyncio
from app.core.config import Settings, get_settings
from app.db.session import dispose_engine, get_engine
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

#: Deliberately not the development database name. See the module docstring.
TEST_DATABASE: Final = "trading_agent_test"

#: Connected to only to issue CREATE/DROP DATABASE, which cannot run inside a
#: transaction and cannot target the database you are connected to.
_MAINTENANCE_DATABASE: Final = "postgres"

_BACKEND_ROOT: Final = Path(__file__).resolve().parents[2]

#: Tables that exist to record the schema version, not application data. They
#: must survive the per-test truncation or every test after the first would run
#: against a database Alembic considers unmigrated.
_NON_DATA_TABLES: Final = frozenset({"alembic_version"})


async def _recreate_database(settings: Settings) -> None:
    """Drop and recreate the test database from the maintenance connection.

    `AUTOCOMMIT` is mandatory, not a shortcut: PostgreSQL refuses
    `CREATE DATABASE` and `DROP DATABASE` inside a transaction block, and
    SQLAlchemy opens one by default.

    `FORCE` terminates any connection left over from a previous run. Without
    it, one abandoned session — a debugger stopped at a breakpoint, a prior
    crashed run — makes `DROP DATABASE` hang until it times out.

    The database name is interpolated rather than bound. It is a module
    constant, never user input, and an identifier cannot be a bind parameter
    in any case; it is quoted so it stays a single identifier regardless.
    """
    engine = create_async_engine(
        settings.database_url.set(database=_MAINTENANCE_DATABASE),
        isolation_level="AUTOCOMMIT",
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE}" WITH (FORCE)')
            )
            await connection.execute(text(f'CREATE DATABASE "{TEST_DATABASE}"'))
    finally:
        await engine.dispose()


def _run_migrations(environment: dict[str, str]) -> None:
    """Bring the fresh database up to `head` using the real migrations.

    Run as a subprocess rather than through Alembic's Python API because
    `alembic/env.py` reads configuration through the cached settings singleton
    and builds its own event loop. Importing it into a running test process
    would mean fighting both. A subprocess gets a clean interpreter, which is
    also how a developer and CI invoke it.
    """
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            "alembic upgrade head failed against the test database:\n"
            f"{result.stdout}\n{result.stderr}"
        )


@pytest.fixture(scope="session")
def database_settings() -> Iterator[Settings]:
    """Point the whole process at a freshly migrated test database.

    The environment is mutated rather than passed around because the engine,
    the seed script and `alembic/env.py` all read the same settings singleton.
    Threading an override through every one of them would be a larger change to
    production code than the tests justify. The original environment is
    restored on the way out.
    """
    original = os.environ.get("POSTGRES_DB")
    os.environ["POSTGRES_DB"] = TEST_DATABASE
    get_settings.cache_clear()
    settings = get_settings()

    try:
        asyncio.run(_recreate_database(settings))
    except (OSError, SQLAlchemyError) as exc:
        get_settings.cache_clear()
        if original is None:
            os.environ.pop("POSTGRES_DB", None)
        else:
            os.environ["POSTGRES_DB"] = original
        pytest.skip(
            "No PostgreSQL reachable at "
            f"{settings.safe_database_url.rsplit('/', 1)[0]} — "
            f"start the stack with `docker compose up -d`. ({type(exc).__name__})"
        )

    _run_migrations({**os.environ, "POSTGRES_DB": TEST_DATABASE})

    try:
        yield settings
    finally:
        asyncio.run(dispose_engine())
        if original is None:
            os.environ.pop("POSTGRES_DB", None)
        else:
            os.environ["POSTGRES_DB"] = original
        get_settings.cache_clear()


@pytest_asyncio.fixture
async def clean_database(database_settings: Settings) -> AsyncIterator[None]:
    """Empty every data table before each test.

    Truncation rather than a rolled-back wrapping transaction, because the code
    under test owns its own transactions: `session_scope` commits, and the seed
    is asserted to be idempotent *across commits*. Nesting all of that inside
    an outer transaction that never commits would test a different program.

    `CASCADE` is required, not lazy: the foreign keys are `RESTRICT` by design
    (see §40 — market history must not vanish because a parent row was
    deleted), so a table-by-table truncate would be refused.

    WHY THE ENGINE IS DISPOSED AFTERWARDS
    -------------------------------------
    pytest-asyncio gives each test its own event loop, while the engine is a
    process-wide singleton holding a pool of asyncpg connections. A connection
    left in the pool is bound to the loop that opened it, so the next test
    borrows a connection whose loop is closed — which surfaced here as
    `RuntimeError: Event loop is closed` raised from pool cleanup, a failure
    with nothing to do with the code under test. Disposing inside the test's
    own loop keeps every connection's lifetime inside the loop that created it.
    """
    engine = get_engine()
    async with engine.begin() as connection:
        rows = await connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        tables = sorted(set(rows.scalars().all()) - _NON_DATA_TABLES)
        if tables:
            targets = ", ".join(f'public."{table}"' for table in tables)
            await connection.execute(
                text(f"TRUNCATE {targets} RESTART IDENTITY CASCADE")
            )
    try:
        yield
    finally:
        await dispose_engine()


@pytest_asyncio.fixture
async def db_session(clean_database: None) -> AsyncIterator[AsyncSession]:
    """A session against the empty test database, committed on success."""
    from app.db.session import session_scope

    async with session_scope() as session:
        yield session


@pytest.fixture
def settings(database_settings: Settings) -> Settings:
    """Override the unit suite's mock-backend settings.

    These tests exist to exercise the PostgreSQL path, so the backend is
    `postgres` and the app is wired to the real repositories.
    """
    return database_settings.model_copy(update={"repository_backend": "postgres"})


@pytest_asyncio.fixture
async def client(
    settings: Settings, clean_database: None
) -> AsyncIterator[AsyncClient]:
    """An HTTP client bound to an app running against the test database."""
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
