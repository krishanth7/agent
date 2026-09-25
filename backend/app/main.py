"""FastAPI application factory.

Current scope: this service exposes read models for the dashboard and a single
writable setting (the monthly target). It has no order path of any kind — not a
disabled one, an absent one.

A broker connection is now possible but is off by default and read-only. Nothing
here establishes it at startup: `angel_one_enabled` must be set, credentials must
be present, and a session is created only when something asks for broker data.
Booting must not cause an outbound call to a broker.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.error_handlers import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import REQUEST_ID_HEADER, request_context_middleware
from app.db.session import dispose_engine
from app.services.broker_service import BrokerService

logger = get_logger(__name__)

_DESCRIPTION = """
Backend foundation for the NIFTY Options Trading Agent dashboard.

**No orders can be placed through this API, and no automated trading exists.**
There is no order endpoint to disable — none is defined. Broker access is
read-only and off unless explicitly configured.

Account and performance figures are mock data. Every payload carries a `source`
field stating its provenance, so a mock figure can never be mistaken for a live
one; check it rather than assuming.
""".strip()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown.

    The database engine is *not* opened here. It is created lazily on first
    use, which means an unreachable database surfaces as a failing request with
    a real error — and a healthy `/health/live` — rather than as a process that
    refuses to boot. Startup that hard-fails on a dependency is how a service
    becomes impossible to diagnose from the outside.

    Shutdown does dispose the pool, so connections are returned to PostgreSQL
    rather than left for its idle timeout to reap. The broker's HTTP pool is
    closed for the same reason — but note what shutdown deliberately does *not*
    do: it does not log out of the broker. A process restarting in five seconds
    should keep a token that is valid until midnight, and discarding it would
    burn a login against a one-per-second limit for nothing.
    """
    settings: Settings = app.state.settings
    logger.info(
        "application_started version=%s environment=%s backend=%s",
        settings.app_version,
        settings.environment,
        settings.repository_backend,
    )
    try:
        yield
    finally:
        # Read off app state rather than held in a variable: the service is
        # created lazily by the first request that needs it, so at startup there
        # is nothing here to close.
        broker_service: BrokerService | None = getattr(
            app.state, "broker_service", None
        )
        if broker_service is not None:
            await broker_service.aclose()
        await dispose_engine()
        logger.info("application_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Takes settings as an argument so tests can construct an app against a
    specific configuration without mutating the process environment.
    """
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=_DESCRIPTION,
        lifespan=lifespan,
        # Interactive docs are a development affordance. In production they are
        # switched off rather than merely unlinked.
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    # Published on app state so dependencies resolve *this* app's settings
    # rather than the process-wide singleton. Without it, the `settings`
    # argument above would govern the title and the CORS policy but not the
    # repository backend, which is exactly the kind of split-brain
    # configuration that makes a test suite lie.
    app.state.settings = settings

    # Explicit origins, never "*". The wildcard is incompatible with
    # `allow_credentials=True` and would be the wrong default regardless.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "PUT", "OPTIONS"],
        allow_headers=["Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )

    app.middleware("http")(request_context_middleware)
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
