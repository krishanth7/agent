"""Async engine, session factory and the request-scoped session dependency.

One engine per process. The engine owns the connection pool, so constructing a
second one silently doubles the connection count against PostgreSQL — which is
how an application that looks fine in development exhausts `max_connections`
in production.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine(settings: Settings) -> AsyncEngine:
    """Build the async engine for a given configuration."""
    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        # Check a pooled connection is still alive before handing it out. The
        # alternative is that the first query after the database restarts
        # fails with a stale-connection error instead of transparently
        # reconnecting — which is precisely the DB-restart scenario this phase
        # has to survive.
        pool_pre_ping=True,
    )


def get_engine() -> AsyncEngine:
    """The process-wide engine, created on first use."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings)
        logger.info("database_engine_created target=%s", settings.safe_database_url)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """The process-wide session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            # Attributes stay loaded after commit. Without this, every ORM
            # object a service returns would re-issue a SELECT on first
            # attribute access after the transaction closed — and raise
            # outright once the session is gone.
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def dispose_engine() -> None:
    """Close the pool and drop the cached engine.

    Called on shutdown, and by tests that need a new engine bound to different
    settings. Leaving the module-level cache populated would hand the next
    caller a session factory bound to a disposed pool.
    """
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        logger.info("database_engine_disposed")
    _engine = None
    _session_factory = None


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """A transactional session for use outside the HTTP layer.

    TRANSACTION BOUNDARY
    --------------------
    The whole block is one transaction: it commits once on success and rolls
    back entirely on any exception. Committing per repository call would make
    a multi-write service operation partially durable, which for financial
    records is worse than failing outright.

    Used by the seed script and by background work. Request handlers get the
    equivalent behaviour from `get_db_session`.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped transactional session.

    The commit happens here rather than in any repository, so one request is
    one transaction regardless of how many repositories it touches. Repository
    methods `flush()` when they need a generated key, and never `commit()`.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            # Roll back and re-raise so the error reaches the translation
            # layer, which decides what the client is told. Swallowing it here
            # would turn a failed write into a silent success.
            await session.rollback()
            raise
