"""User management. Admin-only; the bootstrap admin is protected."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin, verify_csrf
from app.db import get_db
from app.models import Role, User
from app.schemas import UserCreate, UserOut, UserUpdate
from app.services import audit
from app.services.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    _csrf: None = Depends(verify_csrf),
) -> User:
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Логин уже занят")
    if payload.email and db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email уже занят")

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
        is_bootstrap=False,
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        action="user.created",
        entity_type="user",
        entity_id=user.id,
        description=f"Создан пользователь {user.username} с ролью {user.role.value}",
        user=admin,
        changes={"new": {"username": user.username, "role": user.role.value}},
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    _csrf: None = Depends(verify_csrf),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    changes: dict = {"old": {}, "new": {}}
    if payload.email is not None and payload.email != user.email:
        changes["old"]["email"] = user.email
        changes["new"]["email"] = payload.email
        user.email = payload.email
    if payload.is_active is not None and payload.is_active != user.is_active:
        if user.is_bootstrap and not payload.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bootstrap-администратора нельзя деактивировать",
            )
        changes["old"]["is_active"] = user.is_active
        changes["new"]["is_active"] = payload.is_active
        user.is_active = payload.is_active
    if payload.role is not None and payload.role != user.role:
        if user.is_bootstrap and payload.role != Role.admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bootstrap-администратора нельзя понизить в правах",
            )
        changes["old"]["role"] = user.role.value
        changes["new"]["role"] = payload.role.value
        user.role = payload.role
    if payload.password:
        user.password_hash = hash_password(payload.password)
        changes["new"]["password"] = "changed"

    db.flush()
    audit.record(
        db,
        action="user.updated",
        entity_type="user",
        entity_id=user.id,
        description=f"Изменён пользователь {user.username}",
        user=admin,
        changes=changes if changes["new"] else None,
    )
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", response_model=UserOut)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    _csrf: None = Depends(verify_csrf),
) -> User:
    """Deactivate rather than hard-delete so audit history stays intact."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    if user.is_bootstrap:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bootstrap-администратора нельзя удалить",
        )
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нельзя деактивировать собственную учётную запись",
        )
    user.is_active = False
    db.flush()
    audit.record(
        db,
        action="user.deactivated",
        entity_type="user",
        entity_id=user.id,
        description=f"Деактивирован пользователь {user.username}",
        user=admin,
        changes={"old": {"is_active": True}, "new": {"is_active": False}},
    )
    db.commit()
    db.refresh(user)
    return user
