"""Response builders shared by the routers."""
from __future__ import annotations

from app.config import settings
from app.models import Attachment, PaymentOccurrence, RecurringPayment
from app.schemas import OccurrenceOut
from app.services.dates import days_until, local_today
from app.services.status import STATUS_LABELS, compute_status, is_active_overdue


def occurrence_out(
    occurrence: PaymentOccurrence,
    payment: RecurringPayment,
    *,
    today=None,
    attachment_count: int | None = None,
) -> OccurrenceOut:
    if today is None:
        today = local_today(settings.tz)
    status_value = compute_status(
        is_paid=occurrence.is_paid,
        paid_at=occurrence.paid_at,
        due_date=occurrence.due_date,
        today=today,
    )
    return OccurrenceOut(
        id=occurrence.id,
        recurring_payment_id=occurrence.recurring_payment_id,
        due_date=occurrence.due_date,
        amount=occurrence.amount,
        currency=occurrence.currency,
        is_paid=occurrence.is_paid,
        paid_at=occurrence.paid_at,
        receipt_url=occurrence.receipt_url,
        created_at=occurrence.created_at,
        updated_at=occurrence.updated_at,
        status=status_value,
        status_label=STATUS_LABELS[status_value],
        days_until_due=days_until(occurrence.due_date, today),
        is_overdue=is_active_overdue(occurrence.is_paid, occurrence.due_date, today),
        payment_title=payment.title,
        recurrence=payment.recurrence,
        attachment_count=attachment_count if attachment_count is not None else len(occurrence.attachments),
    )
