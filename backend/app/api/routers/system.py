"""Health and integration status endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.db import get_db
from app.models import User
from app.schemas import HealthOut, IntegrationStatus

router = APIRouter(tags=["system"])

VERSION = "1.0.0"


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    """Liveness/readiness probe. Never reveals credentials or internals."""
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_status = "unavailable"
    return HealthOut(
        status="ok" if db_status == "ok" else "degraded",
        database=db_status,
        timezone=settings.APP_TIMEZONE,
        version=VERSION,
    )


@router.get("/integrations", response_model=IntegrationStatus)
def integrations(_user: User = Depends(get_current_user)) -> IntegrationStatus:
    return IntegrationStatus(
        telegram_configured=settings.telegram_enabled,
        telegram_hint=None
        if settings.telegram_enabled
        else "Telegram не настроен: задайте TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID",
        smtp_configured=settings.smtp_enabled,
        smtp_hint=None
        if settings.smtp_enabled
        else "Email не настроен: задайте SMTP_HOST и SMTP_FROM",
    )
