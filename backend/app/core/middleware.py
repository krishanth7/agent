"""Request correlation and access logging.

Implemented as a plain ASGI-level HTTP middleware function rather than a
`BaseHTTPMiddleware` subclass: the latter wraps the response in an extra
task/stream pair, which complicates exception propagation for no benefit here.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Final

from fastapi import Request, Response

from app.core.logging import get_logger, request_id_var

logger = get_logger(__name__)

REQUEST_ID_HEADER: Final = "X-Request-ID"

#: Cap on an inbound correlation ID. Without a bound, a client could push an
#: arbitrarily long string straight into every log line for the request.
_MAX_REQUEST_ID_LENGTH: Final = 128

CallNext = Callable[[Request], Awaitable[Response]]


async def request_context_middleware(request: Request, call_next: CallNext) -> Response:
    """Attach a correlation ID, log the request, and echo the ID back.

    An inbound `X-Request-ID` is honoured so a trace can span the frontend and
    the API; otherwise one is generated. The value is logged but never
    interpreted, and it is length-capped before use.

    Only method, path, status and duration are recorded. Headers, cookies,
    query strings and bodies are deliberately excluded — that is the policy
    that will keep broker credentials out of the logs once they exist.
    """
    incoming = request.headers.get(REQUEST_ID_HEADER, "")
    request_id = incoming[:_MAX_REQUEST_ID_LENGTH] if incoming else uuid.uuid4().hex
    token = request_id_var.set(request_id)

    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - started) * 1000
        # `exception` so the traceback reaches the server log while the client
        # still receives only the generic envelope from the 500 handler.
        logger.exception(
            "request_failed method=%s path=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            duration_ms,
        )
        request_id_var.reset(token)
        raise

    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "request method=%s path=%s status=%d duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )

    response.headers[REQUEST_ID_HEADER] = request_id
    request_id_var.reset(token)
    return response
