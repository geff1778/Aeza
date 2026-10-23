"""Deliver outbox entries through the configured transports."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    NotificationChannel,
    NotificationLog,
    PaymentOccurrence,
    RecurringPayment,
)
from app.services import audit, email as email_transport, notifications, telegram
from app.services.dates import local_today
from app.services.messages import build_message


def build_keyboard(occurrence_id: int) -> dict:
    """Inline keyboard carrying only a trusted server-side identifier."""
    return {
        "inline_keyboard": [
            [{"text": "✅ Оплачено", "callback_data": f"paid:{occurrence_id}"}]
        ]
    }


def deliver_entry(
    db: Session,
    entry: NotificationLog,
    *,
    transport=None,
) -> bool:
    """Deliver a single outbox entry. Returns True on success."""
    occurrence = db.get(PaymentOccurrence, entry.occurrence_id)
    if occurrence is None:
        notifications.mark_failed(db, entry, "occurrence_missing")
        db.commit()
        return False
    payment = db.get(RecurringPayment, occurrence.recurring_payment_id)
    if payment is None:
        notifications.mark_failed(db, entry, "payment_missing")
        db.commit()
        return False

    today = local_today(settings.tz)
    html, plain = build_message(occurrence, payment, kind=entry.kind, today=today)

    if entry.channel == NotificationChannel.telegram:
        result = telegram.send_message(
            html,
            reply_markup=build_keyboard(occurrence.id),
            client=transport,
        )
    else:
        subject = (
            f"Просрочен платёж: {payment.title}"
            if entry.kind.value == "overdue"
            else f"Скоро срок оплаты: {payment.title}"
        )
        result = email_transport.send_email(subject, plain, transport=transport)

    if result.ok:
        notifications.mark_sent(db, entry)
        audit.record(
            db,
            action="notification.sent",
            entity_type="payment_occurrence",
            entity_id=occurrence.id,
            description=(
                f"Уведомление {entry.channel.value}/{entry.kind.value} доставлено "
                f"по платежу «{payment.title}»"
            ),
            actor_label="worker",
        )
        db.commit()
        return True

    notifications.mark_failed(db, entry, result.error or "unknown_error")
    audit.record(
        db,
        action="notification.failed",
        entity_type="payment_occurrence",
        entity_id=occurrence.id,
        description=(
            f"Ошибка доставки {entry.channel.value}/{entry.kind.value} "
            f"для «{payment.title}»: {result.error}"
        ),
        actor_label="worker",
    )
    db.commit()
    return False
