"""Centralized exception rendering.

Every failure leaves the application through one of these handlers and is
rendered into the same envelope::

    {"error": {"code": "...", "message": "..."}}

Nothing else crosses the boundary. Stack traces, filesystem paths, SQL, and
configuration values stay in the server log where they are useful, rather than
in a response where they are an information leak.
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)

#: The only thing a client is ever told about a database failure. Deliberately
#: free of any detail that would describe the deployment — see the handler.
_DATABASE_UNAVAILABLE_MESSAGE = (
    "The service is temporarily unable to reach its data store. "
    "No data has been changed. Please retry shortly."
)


def _envelope(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def _describe_validation_failure(exc: RequestValidationError) -> str:
    """Summarise a validation failure without echoing the submitted value.

    Pydantic's raw error list includes `input`, which would reflect whatever
    the client sent straight back into the response body. Only the field
    location and the rule that failed are surfaced.
    """
    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"] if item != "body")
        parts.append(f"{location}: {error['msg']}" if location else error["msg"])
    return "; ".join(parts) or "Request validation failed."


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        logger.warning("app_error code=%s message=%s", exc.code, exc.message)
        return _envelope(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        message = _describe_validation_failure(exc)
        logger.info("validation_error detail=%s", message)
        # `HTTPStatus` rather than Starlette's constant: the latter is being
        # renamed to HTTP_422_UNPROCESSABLE_CONTENT and emits a deprecation
        # warning on access. The stdlib enum is stable.
        return _envelope(HTTPStatus.UNPROCESSABLE_ENTITY, "VALIDATION_ERROR", message)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        _: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Render framework 404s and 405s in the same envelope as everything else."""
        try:
            code = HTTPStatus(exc.status_code).name
        except ValueError:
            code = "HTTP_ERROR"
        return _envelope(exc.status_code, code, str(exc.detail))

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        """Translate any database failure into a 503 with no driver text.

        WHY THE MESSAGE IS FIXED
        ------------------------
        A SQLAlchemy or asyncpg exception string routinely carries the host,
        port, database name, username, and sometimes the failing SQL with its
        bound parameters — which for this schema means monetary values. None of
        that may cross the boundary. The full exception goes to the log, where
        an operator can see it; the client gets a constant sentence and a
        stable code to branch on.
        """
        logger.exception("database_error type=%s", type(exc).__name__)
        return _envelope(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATABASE_UNAVAILABLE",
            _DATABASE_UNAVAILABLE_MESSAGE,
        )

    @app.exception_handler(OSError)
    async def handle_connection_error(_: Request, exc: OSError) -> JSONResponse:
        """Translate a refused or dropped connection into the same 503.

        Registered separately because a refused TCP connection surfaces as a
        bare `ConnectionRefusedError` from the event loop's socket layer —
        before asyncpg has a DBAPI error to wrap and before SQLAlchemy can
        turn it into an `OperationalError`. Without this handler, stopping the
        database produced an unhandled 500 with a traceback, which is both the
        wrong status and an information leak. Verified against a stopped
        container.
        """
        logger.exception("database_connection_error type=%s", type(exc).__name__)
        return _envelope(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATABASE_UNAVAILABLE",
            _DATABASE_UNAVAILABLE_MESSAGE,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        # The traceback goes to the log; the client gets a generic message.
        logger.exception("unhandled_error type=%s", type(exc).__name__)
        return _envelope(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "An unexpected error occurred.",
        )
