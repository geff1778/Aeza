"""Authentication endpoints: login, me, logout."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CSRF_COOKIE, SESSION_COOKIE, get_current_session, verify_csrf
from app.config import settings
from app.db import get_db
from app.models import User, UserSession
from app.schemas import LoginRequest, MeOut
from app.services import audit
from app.services.rate_limit import login_limiter
from app.services.security import (
    generate_csrf_token,
    generate_session_token,
    hash_session_token,
    session_expiry,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookies(response: Response, token: str, csrf: str, max_age: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        path="/",
    )
    # The CSRF token must be readable by the SPA (double-submit pattern).
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=max_age,
        httponly=False,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        path="/",
    )


def _me_payload(user: User, csrf: str) -> MeOut:
    return MeOut(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        is_bootstrap=user.is_bootstrap,
        created_at=user.created_at,
        csrf_token=csrf,
    )


@router.post("/login", response_model=MeOut)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> MeOut:
    client_ip = request.client.host if request.client else "unknown"
    limit_key = f"{client_ip}:{payload.username}"
    if not login_limiter.allow(limit_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток входа. Попробуйте позже.",
        )

    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        audit.record(
            db,
            action="auth.login_failed",
            entity_type="user",
            entity_id=user.id if user else None,
            description=f"Неудачная попытка входа: {payload.username}",
            actor_label=payload.username,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Учётная запись отключена"
        )

    login_limiter.reset(limit_key)

    token = generate_session_token()
    csrf = generate_csrf_token()
    expires = session_expiry(settings.SESSION_TTL_HOURS)
    db.add(
        UserSession(
            token_hash=hash_session_token(token),
            user_id=user.id,
            expires_at=expires,
            user_agent=(request.headers.get("user-agent") or "")[:255] or None,
        )
    )
    audit.record(
        db,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        description=f"Вход в систему: {user.username}",
        user=user,
    )
    db.commit()
    db.refresh(user)

    _set_session_cookies(response, token, csrf, settings.SESSION_TTL_HOURS * 3600)
    return _me_payload(user, csrf)


@router.get("/me", response_model=MeOut)
def me(
    ctx: tuple[User, UserSession] = Depends(get_current_session),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
) -> MeOut:
    # The CSRF token is echoed back from the readable cookie so a page reload
    # keeps working without exposing anything secret.
    return _me_payload(ctx[0], csrf_cookie or "")


@router.post("/logout", dependencies=[Depends(verify_csrf)])
def logout(
    response: Response,
    ctx: tuple[User, UserSession] = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> dict:
    user, session = ctx
    session.revoked_at = datetime.now(timezone.utc)
    audit.record(
        db,
        action="auth.logout",
        entity_type="user",
        entity_id=user.id,
        description=f"Выход из системы: {user.username}",
        user=user,
    )
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"ok": True}
