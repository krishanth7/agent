"""FastAPI dependency wiring.

This module is the single place that decides *which* repository implementation
the application runs against. Swapping the mocks for PostgreSQL or a broker
adapter in a later phase is an edit here and nowhere else — no route, service
or schema changes.

The repository providers are `lru_cache`d so the whole process shares one
instance. That matters for the target repository, which holds the user's goal
in memory: a fresh instance per request would silently discard every update.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.repositories.interfaces.account_repository import AccountRepository
from app.repositories.interfaces.performance_repository import PerformanceRepository
from app.repositories.interfaces.target_repository import TargetRepository
from app.repositories.mock.account_repository import MockAccountRepository
from app.repositories.mock.performance_repository import MockPerformanceRepository
from app.repositories.mock.target_repository import MockTargetRepository
from app.services.account_service import AccountService
from app.services.agent_service import AgentService
from app.services.performance_service import PerformanceService
from app.services.target_service import TargetService


@lru_cache(maxsize=1)
def get_account_repository() -> AccountRepository:
    return MockAccountRepository()


@lru_cache(maxsize=1)
def get_target_repository() -> TargetRepository:
    return MockTargetRepository()


@lru_cache(maxsize=1)
def get_performance_repository() -> PerformanceRepository:
    return MockPerformanceRepository()


def reset_repositories() -> None:
    """Drop the cached repository singletons.

    Used by the test suite so each test starts from a clean monthly target
    rather than inheriting whatever a previous test wrote.
    """
    get_account_repository.cache_clear()
    get_target_repository.cache_clear()
    get_performance_repository.cache_clear()


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
