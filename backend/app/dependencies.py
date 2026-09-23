"""FastAPI dependency wiring.

This module is the single place that decides *which* repository implementation
the application runs against. Swapping PostgreSQL for a broker adapter in a
later phase is an edit here and nowhere else — no route, service or schema
changes.

BACKEND SELECTION
-----------------
`settings.repository_backend` picks between the PostgreSQL repositories and the
in-memory mocks. The choice is made per request from the settings attached to
the running app, so a test can build an app against a different configuration
without mutating the process environment.

This is a *configuration* switch, not a fallback. Nothing here catches a
connection error and quietly serves mock figures instead: a dashboard that
silently substitutes invented numbers for real ones is worse than a dashboard
that is visibly down.

LIFETIMES
---------
The PostgreSQL repositories are cheap wrappers around the request's session, so
they are constructed per request and must not be cached. The mocks hold process
state — the target mock holds the user's goal in memory — so they stay
`lru_cache`d singletons; a fresh instance per request would silently discard
every update.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import session_scope
from app.repositories.interfaces.account_repository import AccountRepository
from app.repositories.interfaces.performance_repository import PerformanceRepository
from app.repositories.interfaces.target_repository import TargetRepository
from app.repositories.mock.account_repository import MockAccountRepository
from app.repositories.mock.performance_repository import MockPerformanceRepository
from app.repositories.mock.target_repository import MockTargetRepository
from app.repositories.postgres.performance_repository import (
    PostgresPerformanceRepository,
)
from app.repositories.postgres.target_repository import PostgresTargetRepository
from app.services.account_service import AccountService
from app.services.agent_service import AgentService
from app.services.performance_service import PerformanceService
from app.services.target_service import TargetService


def get_app_settings(request: Request) -> Settings:
    """The configuration this particular app was built with.

    Read from app state rather than the module-level singleton so that the
    `settings` argument to `create_app` genuinely governs behaviour. The
    fallback covers an app constructed by something other than the factory.
    """
    settings: Settings | None = getattr(request.app.state, "settings", None)
    return settings if settings is not None else get_settings()


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


async def get_repository_session(
    settings: SettingsDep,
) -> AsyncIterator[AsyncSession | None]:
    """A request-scoped database session, or `None` under the mock backend.

    Yielding `None` rather than declaring the session dependency conditionally
    is what keeps the mock backend usable with no database present: FastAPI
    resolves every declared dependency, so an unconditional session dependency
    would open a connection on every request regardless of backend.

    The session is transactional for the life of the request — one request is
    one transaction, committed here and nowhere else. See `db.session`.
    """
    if settings.repository_backend != "postgres":
        yield None
        return

    async with session_scope() as session:
        yield session


SessionDep = Annotated[AsyncSession | None, Depends(get_repository_session)]


# ---------------------------------------------------------------------------
# Mock singletons
#
# Cached separately from the providers below, because the providers themselves
# take a per-request session and so cannot be cached.
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _mock_account_repository() -> MockAccountRepository:
    return MockAccountRepository()


@lru_cache(maxsize=1)
def _mock_target_repository() -> MockTargetRepository:
    return MockTargetRepository()


@lru_cache(maxsize=1)
def _mock_performance_repository() -> MockPerformanceRepository:
    return MockPerformanceRepository()


def reset_repositories() -> None:
    """Drop the cached mock singletons.

    Used by the test suite so each test starts from a clean monthly target
    rather than inheriting whatever a previous test wrote.
    """
    _mock_account_repository.cache_clear()
    _mock_target_repository.cache_clear()
    _mock_performance_repository.cache_clear()


# ---------------------------------------------------------------------------
# Repository providers
# ---------------------------------------------------------------------------


def get_account_repository() -> AccountRepository:
    """The account funds source.

    ALWAYS MOCK, ON PURPOSE. There is no PostgreSQL account repository and no
    account table, because there is no broker connection to populate one.
    Persisting a balance would make an invented figure look like a settled
    fact — a row in a database reads as authoritative in a way that a literal
    in a mock module does not. The response carries `source: mock` for the
    same reason. This becomes a broker funds call in Phase 4.
    """
    return _mock_account_repository()


def get_target_repository(session: SessionDep) -> TargetRepository:
    if session is None:
        return _mock_target_repository()
    return PostgresTargetRepository(session)


def get_performance_repository(session: SessionDep) -> PerformanceRepository:
    if session is None:
        return _mock_performance_repository()
    return PostgresPerformanceRepository(session)


AccountRepositoryDep = Annotated[AccountRepository, Depends(get_account_repository)]
TargetRepositoryDep = Annotated[TargetRepository, Depends(get_target_repository)]
PerformanceRepositoryDep = Annotated[
    PerformanceRepository, Depends(get_performance_repository)
]


def get_account_service(repository: AccountRepositoryDep) -> AccountService:
    return AccountService(repository)


def get_target_service(repository: TargetRepositoryDep) -> TargetService:
    return TargetService(repository)


def get_performance_service(
    performance_repository: PerformanceRepositoryDep,
    target_repository: TargetRepositoryDep,
) -> PerformanceService:
    return PerformanceService(performance_repository, target_repository)


def get_agent_service() -> AgentService:
    return AgentService()


AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]
TargetServiceDep = Annotated[TargetService, Depends(get_target_service)]
PerformanceServiceDep = Annotated[PerformanceService, Depends(get_performance_service)]
AgentServiceDep = Annotated[AgentService, Depends(get_agent_service)]
