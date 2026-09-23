"""Application error taxonomy.

Every error the API deliberately returns is modelled here so route code can
raise a domain-meaningful exception and let a single handler decide how it is
rendered. Clients receive a stable machine-readable `code`; stack traces,
filesystem paths and configuration never cross the boundary.
"""

from __future__ import annotations

from http import HTTPStatus


class AppError(Exception):
    """Base class for errors that are safe to surface to a client."""

    #: Stable identifier clients may branch on. Never change one casually.
    code: str = "INTERNAL_ERROR"
    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY


class InvalidMonthlyTargetError(AppError):
    code = "INVALID_MONTHLY_TARGET"
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY


class ResourceNotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = HTTPStatus.NOT_FOUND


class PerformanceRecordNotFoundError(ResourceNotFoundError):
    code = "PERFORMANCE_RECORD_NOT_FOUND"


class DatabaseUnavailableError(AppError):
    """The database could not be reached or did not answer.

    503, not 500. The distinction is not cosmetic: 503 says "this request
    would have worked, try again", which is both true and actionable, and it
    is what a load balancer, a retry policy and an orchestrator all key on.
    A 500 says the service is broken and a retry is pointless.

    NO SILENT FALLBACK
    ------------------
    Nothing catches this and substitutes mock figures. A dashboard showing an
    invented ₹4,690 because the database was unreachable is worse than a
    dashboard showing an error — the user would act on a number that describes
    nothing, and would have no way to tell. An outage must look like an outage.
    """

    code = "DATABASE_UNAVAILABLE"
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
