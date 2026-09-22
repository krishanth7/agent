"""Aggregate API router.

INCLUSION ORDER IS SIGNIFICANT: `calendar` must be included before
`performance`, because the latter owns ``/performance/{session_date}`` and
Starlette resolves routes in declaration order. Swapping them would make
``/performance/calendar`` try to parse "calendar" as a date.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import account, agent, calendar, health, performance, targets

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(account.router)
api_router.include_router(targets.router)
api_router.include_router(calendar.router)
api_router.include_router(performance.router)
api_router.include_router(agent.router)
