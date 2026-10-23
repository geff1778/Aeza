"""Recurring payment CRUD. Admin-only for mutations."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin, verify_csrf
from app.api.serializers import occurrence_out
from app.db import get_db
from app.models import Currency, PaymentOccurrence, RecurringPayment, Role, User
from app.schemas import (
    OccurrenceOut,
    RecurringPaymentCreate,
    RecurringPaymentOut,
    RecurringPaymentUpdate,
)
from app.services import payments as payments_service
from app.services.dates import local_today
from app.config import settings

router = APIRouter(prefix="/recurring-payments", tags=["recurring-payments"])


def _counts(db: Session, payment_ids: list[int]) -> dict[int, dict[str, int]]:
    result: dict[int, dict[str, int]] = {pid: {"total": 0, "unpaid": 0, "overdue": 0} for pid in payment_ids}
    if not payment_ids:
        return result
    rows = db.execute(
        select(
            PaymentOccurrence.recurring_payment_id,
            func.count(PaymentOccurrence.id),
            func.count(PaymentOccurrence.id).filter(PaymentOccurrence.is_paid.is_(False)),
            func.count(PaymentOccurrence.id).filter(
                PaymentOccurrence.is_paid.is_(False),
                PaymentOccurrence.due_date < local_today(settings.tz),
            ),
        )
        .where(PaymentOccurrence.recurring_payment_id.in_(payment_ids))
        .group_by(PaymentOccurrence.recurring_payment_id)
    ).all()
    for pid, total, unpaid, overdue in rows:
        result[pid] = {"total": total, "unpaid": unpaid, "overdue": overdue}
    return result


def _serialize(payment: RecurringPayment, counts: dict[str, int]) -> RecurringPaymentOut:
    return RecurringPaymentOut(
        id=payment.id,
        title=payment.title,
        description=payment.description,
        amount=payment.amount,
        currency=payment.currency,
        recurrence=payment.recurrence,
        anchor_day=payment.anchor_day,
        first_due_date=payment.first_due_date,
        is_active=payment.is_active,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
        occurrences_count=counts["total"],
        unpaid_count=counts["unpaid"],
        overdue_count=counts["overdue"],
    )


@router.get("", response_model=list[RecurringPaymentOut])
def list_recurring_payments(
    include_inactive: bool = Query(default=True),
    currency: Currency | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RecurringPaymentOut]:
    stmt = select(RecurringPayment)
    if not include_inactive:
        stmt = stmt.where(RecurringPayment.is_active.is_(True))
    if currency is not None:
        stmt = stmt.where(RecurringPayment.currency == currency)
    if search:
        stmt = stmt.where(RecurringPayment.title.ilike(f"%{search}%"))
    stmt = stmt.order_by(RecurringPayment.is_active.desc(), RecurringPayment.title)
    payments = list(db.scalars(stmt))
    counts = _counts(db, [p.id for p in payments])
    return [_serialize(p, counts[p.id]) for p in payments]


@router.post("", response_model=RecurringPaymentOut, status_code=status.HTTP_201_CREATED)
def create_recurring_payment(
    payload: RecurringPaymentCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    _csrf: None = Depends(verify_csrf),
) -> RecurringPaymentOut:
    try:
        payment = payments_service.create_recurring_payment(
            db,
            actor=admin,
            title=payload.title,
            amount=payload.amount,
            currency=payload.currency,
            first_due_date=payload.first_due_date,
            recurrence=payload.recurrence,
            anchor_day=payload.anchor_day,
            description=payload.description,
        )
    except payments_service.DomainError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    counts = _counts(db, [payment.id])
    return _serialize(payment, counts[payment.id])


@router.get("/{payment_id}", response_model=RecurringPaymentOut)
def get_recurring_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RecurringPaymentOut:
    payment = db.get(RecurringPayment, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Платёж не найден")
    counts = _counts(db, [payment.id])
    return _serialize(payment, counts[payment.id])


@router.get("/{payment_id}/history", response_model=list[OccurrenceOut])
def get_history(
    payment_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[OccurrenceOut]:
    payment = db.get(RecurringPayment, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Платёж не найден")
    rows = list(
        db.scalars(
            select(PaymentOccurrence)
            .where(PaymentOccurrence.recurring_payment_id == payment_id)
            .order_by(PaymentOccurrence.due_date.desc())
        )
    )
    return [occurrence_out(o, payment) for o in rows]


@router.patch("/{payment_id}", response_model=RecurringPaymentOut)
def update_recurring_payment(
    payment_id: int,
    payload: RecurringPaymentUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    _csrf: None = Depends(verify_csrf),
) -> RecurringPaymentOut:
    payment = db.get(RecurringPayment, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Платёж не найден")
    try:
        payment = payments_service.update_recurring_payment(
            db, actor=admin, payment=payment, **payload.model_dump(exclude_unset=True)
        )
    except payments_service.DomainError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    counts = _counts(db, [payment.id])
    return _serialize(payment, counts[payment.id])


@router.delete("/{payment_id}", response_model=RecurringPaymentOut)
def complete_recurring_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    _csrf: None = Depends(verify_csrf),
) -> RecurringPaymentOut:
    """Soft-complete: stops generation and reminders, keeps the full history."""
    payment = db.get(RecurringPayment, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Платёж не найден")
    payment = payments_service.deactivate_recurring_payment(db, actor=admin, payment=payment)
    counts = _counts(db, [payment.id])
    return _serialize(payment, counts[payment.id])
