"""Audit logging. Audit records are always written by server-side logic."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User

_SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "token_hash",
    "secret",
    "secret_key",
    "cookie",
    "authorization",
    "smtp_password",
    "bot_token",
}


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("***" if k.lower() in _SENSITIVE_KEYS else _sanitize(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def record(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | int | None,
    description: str,
    user: User | None = None,
    actor_label: str | None = None,
    changes: dict | None = None,
    request_id: str | None = None,
) -> AuditLog:
    label = actor_label or (user.username if user else "system")
    entry = AuditLog(
        user_id=user.id if user else None,
        actor_label=label,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        description=description,
        changes=_sanitize(changes) if changes else None,
        request_id=request_id,
    )
    db.add(entry)
    db.flush()
    return entry
