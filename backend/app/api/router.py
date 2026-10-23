"""Router registry for API v1."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import (
    admin,
    analytics,
    attachments,
    auth,
    budgets,
    occurrences,
    recurring_payments,
    system,
    users,
)

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(recurring_payments.router)
api_router.include_router(occurrences.router)
api_router.include_router(analytics.router)
api_router.include_router(users.router)
api_router.include_router(budgets.router)
api_router.include_router(admin.router)
api_router.include_router(attachments.router)
