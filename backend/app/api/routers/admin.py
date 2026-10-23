"""Audit log and notification log views. Admin-only."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db import get_db
from app.models import AuditLog, NotificationLog, User
from app.schemas import AuditListOut, AuditOut, NotificationLogOut

router = APIRouter(tags=["admin"])


@router.get("/audit", response_model=AuditListOut)
def list_audit(
    action: str | None = None,
    user_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> AuditListOut:
    stmt = select(AuditLog)
    count_stmt = select(func.count(AuditLog.id))
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"%{action}%"))
        count_stmt = count_stmt.where(AuditLog.action.ilike(f"%{action}%"))
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
        count_stmt = count_stmt.where(AuditLog.user_id == user_id)
    if date_from is not None:
        stmt = stmt.where(func.date(AuditLog.created_at) >= date_from)
        count_stmt = count_stmt.where(func.date(AuditLog.created_at) >= date_from)
    if date_to is not None:
        stmt = stmt.where(func.date(AuditLog.created_at) <= date_to)
        count_stmt = count_stmt.where(func.date(AuditLog.created_at) <= date_to)

    total = db.scalar(count_stmt) or 0
    items = list(
        db.scalars(stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit))
    )
    return AuditListOut(items=[AuditOut.model_validate(i) for i in items], total=total)


@router.get("/notifications", response_model=list[NotificationLogOut])
def list_notifications(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[NotificationLogOut]:
    items = list(
        db.scalars(select(NotificationLog).order_by(NotificationLog.created_at.desc()).limit(limit))
    )
    return [NotificationLogOut.model_validate(i) for i in items]
