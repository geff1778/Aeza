"""Payment domain service — the only place payment state is mutated.

Both the web panel and the Telegram callback use these functions, so status
semantics are identical everywhere.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Currency,
    PaymentOccurrence,
    Recurrence,
    RecurringPayment,
    User,
)
from app.services import audit
from app.services.dates import local_today
from app.services.generation import ensure_periods


class DomainError(Exception):
    """Raised when a domain rule is violated."""


def _changes(before: dict, after: dict) -> dict:
    return {
        "old": {k: before[k] for k in before if before[k] != after.get(k)},
        "new": {k: after[k] for k in after if before.get(k) != after[k]},
    }


def create_recurring_payment(
    db: Session,
    *,
    actor: User,
    title: str,
    amount: Decimal,
    currency: Currency,
    first_due_date: date,
    recurrence: Recurrence = Recurrence.monthly,
    anchor_day: int | None = None,
    description: str | None = None,
) -> RecurringPayment:
    if amount <= 0:
        raise DomainError("Сумма должна быть больше нуля")
    anchor = first_due_date.day if anchor_day is None else anchor_day
    if not 1 <= anchor <= 31:
        raise DomainError("День месяца должен быть в диапазоне 1..31")

    payment = RecurringPayment(
        title=title,
        description=description,
        amount=amount,
        currency=currency,
        recurrence=recurrence,
        anchor_day=anchor,
        first_due_date=first_due_date,
        is_active=True,
        created_by_id=actor.id,
    )
    db.add(payment)
    db.flush()

    today = local_today(settings.tz)
    ensure_periods(db, payment, today)

    audit.record(
        db,
        action="recurring_payment.created",
        entity_type="recurring_payment",
        entity_id=payment.id,
        description=f"Создан регулярный платёж «{payment.title}»",
        user=actor,
        changes={
            "new": {
                "title": title,
                "amount": str(amount),
                "currency": currency.value,
                "first_due_date": first_due_date.isoformat(),
                "recurrence": recurrence.value,
                "anchor_day": anchor,
            }
        },
    )
    db.commit()
    db.refresh(payment)
    return payment


def update_recurring_payment(
    db: Session,
    *,
    actor: User,
    payment: RecurringPayment,
    **fields,
) -> RecurringPayment:
    allowed = {
        "title",
        "description",
        "amount",
        "currency",
        "recurrence",
        "anchor_day",
        "first_due_date",
        "is_active",
    }
    before = {k: getattr(payment, k) for k in allowed}
    before = {
        k: (v.value if hasattr(v, "value") else (v.isoformat() if isinstance(v, date) else v))
        for k, v in before.items()
    }

    for key, value in fields.items():
        if key in allowed and value is not None:
            setattr(payment, key, value)

    if payment.amount <= 0:
        raise DomainError("Сумма должна быть больше нуля")
    if not 1 <= payment.anchor_day <= 31:
        raise DomainError("День месяца должен быть в диапазоне 1..31")

    db.flush()
    # Re-materialise future periods if the schedule changed.
    if any(k in fields for k in ("first_due_date", "anchor_day", "recurrence")):
        ensure_periods(db, payment, local_today(settings.tz))

    after = {
        k: (
            getattr(payment, k).value
            if hasattr(getattr(payment, k), "value")
            else (
                getattr(payment, k).isoformat()
                if isinstance(getattr(payment, k), date)
                else getattr(payment, k)
            )
        )
        for k in allowed
    }
    audit.record(
        db,
        action="recurring_payment.updated",
        entity_type="recurring_payment",
        entity_id=payment.id,
        description=f"Изменён регулярный платёж «{payment.title}»",
        user=actor,
        changes=_changes(before, after),
    )
    db.commit()
    db.refresh(payment)
    return payment


def deactivate_recurring_payment(
    db: Session, *, actor: User, payment: RecurringPayment
) -> RecurringPayment:
    """Stop future generation and reminders while keeping the whole history."""
    if not payment.is_active:
        return payment
    payment.is_active = False
    payment.deleted_at = datetime.now(timezone.utc)
    db.flush()
    audit.record(
        db,
        action="recurring_payment.completed",
        entity_type="recurring_payment",
        entity_id=payment.id,
        description=f"Завершён регулярный платёж «{payment.title}»",
        user=actor,
        changes={"old": {"is_active": True}, "new": {"is_active": False}},
    )
    db.commit()
    db.refresh(payment)
    return payment


def mark_paid(
    db: Session,
    *,
    actor: User,
    occurrence: PaymentOccurrence,
    paid_at: date | None = None,
    actor_label: str | None = None,
    request_id: str | None = None,
) -> PaymentOccurrence:
    today = local_today(settings.tz)
    effective = paid_at or today

    if occurrence.is_paid and occurrence.paid_at == effective:
        # Idempotent: pressing "Paid" twice changes nothing.
        return occurrence

    before = {"is_paid": occurrence.is_paid, "paid_at": occurrence.paid_at}
    occurrence.is_paid = True
    occurrence.paid_at = effective
    occurrence.paid_by_id = actor.id
    db.flush()

    late = effective > occurrence.due_date
    audit.record(
        db,
        action="payment_occurrence.marked_paid",
        entity_type="payment_occurrence",
        entity_id=occurrence.id,
        description=(
            f"Платёж за {occurrence.due_date.isoformat()} отмечен оплаченным"
            + (" с просрочкой" if late else " вовремя")
        ),
        user=actor,
        actor_label=actor_label,
        changes={
            "old": {
                "is_paid": before["is_paid"],
                "paid_at": before["paid_at"].isoformat() if before["paid_at"] else None,
            },
            "new": {"is_paid": True, "paid_at": effective.isoformat()},
        },
        request_id=request_id,
    )
    db.commit()
    db.refresh(occurrence)
    return occurrence


def unmark_paid(
    db: Session,
    *,
    actor: User,
    occurrence: PaymentOccurrence,
    request_id: str | None = None,
) -> PaymentOccurrence:
    """Cancel a mistaken payment mark. The occurrence row is never deleted."""
    if not occurrence.is_paid:
        return occurrence

    before = occurrence.paid_at
    occurrence.is_paid = False
    occurrence.paid_at = None
    occurrence.paid_by_id = None
    db.flush()

    today = local_today(settings.tz)
    audit.record(
        db,
        action="payment_occurrence.unmarked_paid",
        entity_type="payment_occurrence",
        entity_id=occurrence.id,
        description=f"Отменена отметка об оплате периода {occurrence.due_date.isoformat()}",
        user=actor,
        changes={
            "old": {"is_paid": True, "paid_at": before.isoformat() if before else None},
            "new": {"is_paid": False, "paid_at": None},
        },
        request_id=request_id,
    )
    db.commit()
    db.refresh(occurrence)
    return occurrence


def update_occurrence(
    db: Session,
    *,
    actor: User,
    occurrence: PaymentOccurrence,
    is_paid: bool | None = None,
    paid_at: date | None = None,
    receipt_url: str | None = None,
    request_id: str | None = None,
) -> PaymentOccurrence:
    """Apply a partial update to a period, recalculating status implicitly."""
    changed: dict[str, dict] = {}

    if receipt_url is not None and receipt_url != occurrence.receipt_url:
        changed["receipt_url"] = {"old": occurrence.receipt_url, "new": receipt_url}
        occurrence.receipt_url = receipt_url or None

    if is_paid is False:
        if occurrence.is_paid:
            before = occurrence.paid_at
            occurrence.is_paid = False
            occurrence.paid_at = None
            occurrence.paid_by_id = None
            changed["is_paid"] = {
                "old": True,
                "new": False,
                "paid_at_old": before.isoformat() if before else None,
            }
    elif is_paid is True or paid_at is not None:
        effective = paid_at or occurrence.paid_at or local_today(settings.tz)
        before = {"is_paid": occurrence.is_paid, "paid_at": occurrence.paid_at}
        occurrence.is_paid = True
        occurrence.paid_at = effective
        occurrence.paid_by_id = actor.id
        changed["is_paid"] = {
            "old": before["is_paid"],
            "new": True,
            "paid_at_old": before["paid_at"].isoformat() if before["paid_at"] else None,
            "paid_at_new": effective.isoformat(),
        }

    if not changed:
        return occurrence

    db.flush()
    audit.record(
        db,
        action="payment_occurrence.updated",
        entity_type="payment_occurrence",
        entity_id=occurrence.id,
        description=f"Изменён период {occurrence.due_date.isoformat()}",
        user=actor,
        changes=changed,
        request_id=request_id,
    )
    db.commit()
    db.refresh(occurrence)
    return occurrence


def list_occurrences(
    db: Session,
    *,
    status: str | None = None,
    currency: Currency | None = None,
    recurring_payment_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    sort: str = "due_date",
    direction: str = "asc",
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[tuple[PaymentOccurrence, RecurringPayment]], int]:
    from app.services.status import compute_status

    stmt = select(PaymentOccurrence, RecurringPayment).join(
        RecurringPayment, PaymentOccurrence.recurring_payment_id == RecurringPayment.id
    )
    if currency is not None:
        stmt = stmt.where(PaymentOccurrence.currency == currency)
    if recurring_payment_id is not None:
        stmt = stmt.where(PaymentOccurrence.recurring_payment_id == recurring_payment_id)
    if date_from is not None:
        stmt = stmt.where(PaymentOccurrence.due_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(PaymentOccurrence.due_date <= date_to)
    if search:
        stmt = stmt.where(RecurringPayment.title.ilike(f"%{search}%"))

    # Sorting is whitelisted so the column name can never reach SQL directly.
    # Default is ascending due_date: the most urgent period comes first, which
    # is what the payments table and dashboard need.
    sortable = {
        "due_date": PaymentOccurrence.due_date,
        "amount": PaymentOccurrence.amount,
        "created_at": PaymentOccurrence.created_at,
    }
    column = sortable.get(sort, PaymentOccurrence.due_date)
    order = column.asc() if direction == "asc" else column.desc()
    stmt = stmt.order_by(order, PaymentOccurrence.id.asc())

    rows = db.execute(stmt).all()
    today = local_today(settings.tz)
    if status:
        rows = [
            (o, p)
            for o, p in rows
            if compute_status(is_paid=o.is_paid, paid_at=o.paid_at, due_date=o.due_date, today=today)
            == status
        ]
    total = len(rows)
    return rows[offset : offset + limit], total
