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
