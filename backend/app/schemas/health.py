"""Health API schema."""

from __future__ import annotations

from typing import Literal

from app.schemas.common import ApiModel


class HealthResponse(ApiModel):
    """Liveness and identity of the running service.

    Deliberately free of build paths, hostnames and configuration: a health
    endpoint is usually the least protected route in a system, so it should
    reveal nothing an attacker could use to fingerprint the deployment beyond
    the version already published in the OpenAPI document.
    """

    status: Literal["ok"]
    service: str
    version: str
    environment: str
