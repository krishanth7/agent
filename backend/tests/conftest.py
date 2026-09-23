"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from app.core.config import Settings
from app.dependencies import reset_repositories
from app.main import create_app
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _isolate_repositories() -> Iterator[None]:
    """Give every test a fresh set of repository singletons.

    The mock target repository holds state for the process lifetime, which is
    correct in production but would otherwise let one test's PUT leak into the
    next test's GET.
    """
    reset_repositories()
    yield
    reset_repositories()


@pytest.fixture
def settings() -> Settings:
    """Configuration for the database-free unit suite.

    `repository_backend="mock"` is explicit rather than inherited. These tests
    cover routing, validation, serialization and the calculation rules — none
    of which involve SQL — so binding them to a live PostgreSQL would make them
    slower and able to fail for reasons that have nothing to do with what they
    assert.

    The PostgreSQL repositories are not left untested by this: they are covered
    against a real database in `tests/integration`, which is where persistence
    and restart survival are proven.
    """
    return Settings(
        environment="development",
        cors_origins=["http://localhost:3000"],
        log_level="WARNING",
        repository_backend="mock",
    )


@pytest_asyncio.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    """An HTTP client bound directly to the ASGI app — no socket involved."""
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
def api(settings: Settings) -> str:
    return settings.api_v1_prefix
