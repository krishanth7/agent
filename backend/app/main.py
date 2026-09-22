"""FastAPI application factory.

Phase 2 scope: this service exposes read models for the dashboard and a single
writable setting (the monthly target). It connects to no broker, subscribes to
no market-data feed, and has no order path of any kind.
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

logger = get_logger(__name__)

_DESCRIPTION = """
Backend foundation for the NIFTY Options Trading Agent dashboard.

**All trading and account figures served by this API are mock data.**
No broker is connected, no market-data feed is subscribed, no orders can be
placed, and no automated trading exists. Every payload carries a `source`
field stating its provenance.
""".strip()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown.

    Nothing is initialised here. Connection pools, broker sessions and
    market-data subscriptions belong to the phases that introduce them; opening
    a pool for a database that does not exist would be ceremony, not
    architecture.
    """
    settings = get_settings()
    logger.info(
        "application_started version=%s environment=%s",
        settings.app_version,
        settings.environment,
    )
    yield
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
