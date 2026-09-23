"""Alembic environment, wired for async SQLAlchemy.

The application talks to PostgreSQL over asyncpg, so migrations do too — a
second, synchronous driver would be an extra dependency and an extra way for
the two to disagree about types. Alembic's migration engine is synchronous, so
the async connection is bridged with `run_sync`.

The database URL comes from application settings, never from `alembic.ini`,
so a password is never written to a committed file.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import Any

# Importing the model registry is what populates `Base.metadata`. Without it
# autogenerate would compare against an empty schema and cheerfully propose
# dropping every table.
import app.db.models  # noqa: F401  (imported for its side effect)
from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """Render the connection URL with the password included.

    `render_as_string(hide_password=False)` is required: the default masks the
    password as `***`, which produces an authentication failure that looks
    like a wrong credential rather than a formatting mistake.
    """
    return get_settings().database_url.render_as_string(hide_password=False)


def include_object(
    obj: Any,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: Any,
) -> bool:
    """Keep TimescaleDB's internal objects out of autogenerate.

    Creating a hypertable causes Timescale to materialise chunk tables in its
    own schemas. They are reflected like any other table, and without this
    filter every autogenerate run would propose dropping them — which would
    delete market data.
    """
    if type_ == "table":
        schema = getattr(obj, "schema", None)
        if schema in _TIMESCALE_SCHEMAS:
            return False
    return True


_TIMESCALE_SCHEMAS = {
    "_timescaledb_internal",
    "_timescaledb_catalog",
    "_timescaledb_config",
    "_timescaledb_cache",
    "timescaledb_information",
    "timescaledb_experimental",
}


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting.

    Used to review the exact DDL a migration would run before letting it near
    a database that holds real trading history.
    """
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        # Detect column type changes as well as added/dropped columns.
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        # Migrations are a short-lived, single-connection operation. Pooling
        # would hold a connection open after the process is done with it.
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
