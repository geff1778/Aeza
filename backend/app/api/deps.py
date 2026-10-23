"""FastAPI dependencies: authentication, authorization and CSRF checks."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Role, User, UserSession
from app.services.security import constant_time_equals, hash_session_token

SESSION_COOKIE = settings.SESSION_COOKIE_NAME
CSRF_COOKIE = f"{SESSION_COOKIE}_csrf"


def _unauthorized(detail: str = "Требуется аутентификация") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def get_current_session(
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> tuple[User, UserSession]:
    if not session_token:
        raise _unauthorized()

    token_hash = hash_session_token(session_token)
    row = db.execute(
        select(UserSession, User)
        .join(User, UserSession.user_id == User.id)
        .where(UserSession.token_hash == token_hash)
    ).first()
    if row is None:
        raise _unauthorized("Сессия не найдена")

    session, user = row
    if session.revoked_at is not None:
        raise _unauthorized("Сессия отозвана")
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise _unauthorized("Сессия истекла")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Учётная запись отключена")
    return user, session


def get_current_user(
    ctx: tuple[User, UserSession] = Depends(get_current_session),
) -> User:
    return ctx[0]


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Server-side admin gate — hiding buttons in React is never enough."""
    if user.role != Role.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права администратора",
        )
    return user


def verify_csrf(
    request: Request,
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> None:
    """Double-submit cookie check for state-changing requests."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if not csrf_cookie or not x_csrf_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Отсутствует CSRF-токен")
    if not constant_time_equals(csrf_cookie, x_csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Неверный CSRF-токен")


def request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)
