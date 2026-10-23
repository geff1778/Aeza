"""Payment status computation — a single source of truth for the whole product.

The status belongs to the *payment occurrence* (a shared record), never to an
individual user, so every user sees the same value.
"""
from __future__ import annotations

from datetime import date
from enum import Enum

from app.config import settings
from app.services.dates import local_today


class PaymentStatus(str, Enum):
    paid_on_time = "paid_on_time"
    paid_late = "paid_late"
    overdue = "overdue"
    due_soon = "due_soon"
    pending = "pending"


STATUS_LABELS: dict[str, str] = {
    "paid_on_time": "Оплачено вовремя",
    "paid_late": "Оплачено с просрочкой",
    "overdue": "Просрочено",
    "due_soon": "Скоро срок",
    "pending": "Ожидает оплаты",
}


def compute_status(
    *,
    is_paid: bool,
    paid_at: date | None,
    due_date: date,
    today: date | None = None,
    due_soon_days: int | None = None,
) -> str:
    """Return the status string for an occurrence.

    Rules:
      * unpaid and today > due_date          -> overdue
      * unpaid and 0 <= days <= due_soon     -> due_soon
      * unpaid and days > due_soon           -> pending
      * paid and paid_at <= due_date         -> paid_on_time
      * paid and paid_at >  due_date         -> paid_late
    """
    if today is None:
        today = local_today(settings.tz)
    if due_soon_days is None:
        due_soon_days = settings.REMINDER_DAYS_BEFORE

    if is_paid:
        if paid_at is None:
            # Paid flag without a recorded date: treat the payment date as due date.
            return PaymentStatus.paid_on_time.value
        return (
            PaymentStatus.paid_on_time.value
            if paid_at <= due_date
            else PaymentStatus.paid_late.value
        )

    if today > due_date:
        return PaymentStatus.overdue.value
    if (due_date - today).days <= due_soon_days:
        return PaymentStatus.due_soon.value
    return PaymentStatus.pending.value


def is_active_overdue(is_paid: bool, due_date: date, today: date | None = None) -> bool:
    if today is None:
        today = local_today(settings.tz)
    return (not is_paid) and today > due_date
