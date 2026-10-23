"""Period materialisation for recurring payments.

Generation is independent of previous payment status: an overdue October period
never blocks the creation of November or December periods. Idempotency is
enforced by the ``uq_occurrence_period`` unique constraint plus an
``ON CONFLICT DO NOTHING`` insert, so concurrent runs are safe.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PaymentOccurrence, RecurringPayment
from app.services.dates import add_months_anchored, iter_due_dates, local_today


def horizon_end(today: date, months: int) -> date:
    return add_months_anchored(today.year, today.month, months, today.day)


def ensure_periods(db: Session, payment: RecurringPayment, today: date | None = None) -> int:
    """Materialise all missing periods up to the horizon. Returns rows created."""
    if today is None:
        today = local_today(settings.tz)
    if not payment.is_active:
        return 0

    until = horizon_end(today, settings.GENERATION_HORIZON_MONTHS)
    if payment.first_due_date > until:
        return 0

    due_dates = iter_due_dates(
        payment.first_due_date, payment.recurrence, payment.anchor_day, until
    )
    if not due_dates:
        return 0

    rows = [
        {
            "recurring_payment_id": payment.id,
            "due_date": d,
            "amount": payment.amount,
            "currency": payment.currency,
            "is_paid": False,
        }
        for d in due_dates
    ]

    stmt = pg_insert(PaymentOccurrence).values(rows)
    stmt = stmt.on_conflict_do_nothing(constraint="uq_occurrence_period").returning(
        PaymentOccurrence.id
    )
    # RETURNING only produces rows for real inserts, so this count is exact.
    created = len(db.execute(stmt).fetchall())
    db.flush()
    return created


def ensure_all_periods(db: Session, today: date | None = None) -> int:
    """Materialise periods for every active recurring payment."""
    payments = db.scalars(select(RecurringPayment).where(RecurringPayment.is_active.is_(True)))
    created = 0
    for payment in payments:
        created += ensure_periods(db, payment, today)
    return created
