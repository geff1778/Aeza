"""Telegram callback handling for the inline "Оплачено" button.

The callback carries only a trusted occurrence id; amounts, currencies and dates
are never taken from the client. The same domain service used by the web panel
performs the change, so the status is identical for everyone.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PaymentOccurrence, RecurringPayment, User
from app.services import payments as payments_service
from app.services.dates import local_today
from app.services.messages import format_amount, format_date_ru


def is_allowed_user(telegram_user_id: int | None, chat_id: str | int | None) -> bool:
    """Restrict button presses to configured chats/users when a list is set."""
    allowed = settings.telegram_allowed_user_ids
    if not allowed:
        return True
    if telegram_user_id is not None and telegram_user_id in allowed:
        return True
    if chat_id is not None:
        try:
            return int(chat_id) in allowed
        except (TypeError, ValueError):
            return False
    return False


def _system_actor(db: Session) -> User:
    actor = db.scalar(
        select(User).where(User.role == "admin", User.is_active.is_(True)).order_by(User.id)
    )
    if actor is None:
        actor = db.scalar(select(User).order_by(User.id))
    if actor is None:
        raise RuntimeError("no_users")
    return actor


def handle_paid_callback(db: Session, data: str, *, actor_label: str = "telegram") -> str:
    """Process callback data of the form ``paid:<occurrence_id>``.

    Returns a human-readable answer for the callback toast.
    """
    if not data.startswith("paid:"):
        return "Неизвестное действие"
    raw_id = data.split(":", 1)[1]
    if not raw_id.isdigit():
        return "Некорректный идентификатор платежа"

    occurrence = db.get(PaymentOccurrence, int(raw_id))
    if occurrence is None:
        return "Период не найден"

    payment = db.get(RecurringPayment, occurrence.recurring_payment_id)
    if payment is None:
        return "Платёж не найден"
    if not payment.is_active:
        return "Регулярный платёж завершён"
    if occurrence.is_paid:
        return "Уже отмечено как оплачено"

    actor = _system_actor(db)
    payments_service.mark_paid(
        db, actor=actor, occurrence=occurrence, actor_label=actor_label
    )
    today = local_today(settings.tz)
    amount = format_amount(occurrence.amount, occurrence.currency.value)
    due = format_date_ru(occurrence.due_date)
    if occurrence.paid_at and occurrence.paid_at > occurrence.due_date:
        return f"Оплачено с просрочкой: {payment.title}, {amount}, срок {due}"
    return f"Оплачено вовремя: {payment.title}, {amount}, срок {due}"
