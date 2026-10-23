"""Payment occurrence endpoints — shared status for every user."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, verify_csrf
from app.api.serializers import occurrence_out
from app.db import get_db
from app.models import Currency, PaymentOccurrence, RecurringPayment, User
from app.schemas import OccurrenceListOut, OccurrenceOut, OccurrenceUpdate
from app.services import payments as payments_service

router = APIRouter(prefix="/payment-occurrences", tags=["payment-occurrences"])


@router.get("", response_model=OccurrenceListOut)
def list_occurrences(
    status_filter: str | None = Query(default=None, alias="status"),
    currency: Currency | None = None,
    recurring_payment_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    sort: str = Query(default="due_date", pattern="^(due_date|amount|created_at)$"),
    direction: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> OccurrenceListOut:
    rows, total = payments_service.list_occurrences(
        db,
        status=status_filter,
        currency=currency,
        recurring_payment_id=recurring_payment_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
        sort=sort,
        direction=direction,
        limit=limit,
        offset=offset,
    )
    return OccurrenceListOut(
        items=[occurrence_out(o, p) for o, p in rows],
        total=total,
    )


def _load(db: Session, occurrence_id: int) -> tuple[PaymentOccurrence, RecurringPayment]:
    occurrence = db.get(PaymentOccurrence, occurrence_id)
    if occurrence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Период не найден")
    payment = db.get(RecurringPayment, occurrence.recurring_payment_id)
    return occurrence, payment


@router.get("/{occurrence_id}", response_model=OccurrenceOut)
def get_occurrence(
    occurrence_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> OccurrenceOut:
    occurrence, payment = _load(db, occurrence_id)
    return occurrence_out(occurrence, payment)


@router.patch("/{occurrence_id}", response_model=OccurrenceOut)
def update_occurrence(
    occurrence_id: int,
    payload: OccurrenceUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _csrf: None = Depends(verify_csrf),
) -> OccurrenceOut:
    """Mark paid, correct the actual payment date, or clear a mistaken mark.

    Available to every authenticated user because the payment status is shared.
    """
    occurrence, payment = _load(db, occurrence_id)
    if payload.is_paid is False and payload.paid_at is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Нельзя одновременно снять отметку и указать дату оплаты",
        )
    occurrence = payments_service.update_occurrence(
        db,
        actor=user,
        occurrence=occurrence,
        is_paid=payload.is_paid,
        paid_at=payload.paid_at,
        receipt_url=payload.receipt_url,
        request_id=getattr(request.state, "request_id", None),
    )
    return occurrence_out(occurrence, payment)
