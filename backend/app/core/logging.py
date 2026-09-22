"""Logging configuration and request-correlation plumbing.

The correlation ID lives in a `ContextVar` and is injected into every record by
a logging filter, so service and repository code never has to thread a request
ID through its signatures just to produce a traceable log line.

SECURITY: this module deliberately logs only method, path, status, duration and
the correlation ID. Request headers, cookies, query strings and bodies are
never logged. Once broker credentials and auth tokens enter the system in a
later phase, that policy must hold — the safest way to keep secrets out of logs
is to never start logging the containers they travel in.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Final

from app.core.config import Settings

#: Correlation ID for the in-flight request. "-" when outside a request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_LOG_FORMAT: Final = (
    "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"
)


class RequestIdFilter(logging.Filter):
    """Attaches the current correlation ID to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(settings: Settings) -> None:
    """Install a single stdout handler on the root logger.

    Idempotent: re-running it (as the test suite does when it rebuilds the app)
    replaces the handler rather than stacking duplicates.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(settings.log_level)

    # Uvicorn installs its own access log with a different format; ours already
    # records method/path/status/duration with the correlation ID attached.
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
