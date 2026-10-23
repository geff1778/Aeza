"""Notification rules and outbox materialisation.

This module owns the *decision* about what should be notified; transports
(Telegram, email) only deliver what the outbox already contains. Because the
outbox has a unique constraint on (occurrence, channel, kind), re-running the
worker can never duplicate a notification.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    DeliveryStatus,
    NotificationChannel,
    NotificationKind,
    NotificationLog,
    PaymentOccurrence,
    RecurringPayment,
)
from app.services.dates import local_today


def should_notify_reminder(
    *, is_paid: bool, due_date: date, today: date, days_before: int
) -> bool:
    """Reminder is due when the period is unpaid and the deadline is within the
    reminder window (or already passed but still unpaid -> overdue notice)."""
    if is_paid:
        return False
    return (due_date - today).days <= days_before


def kind_for(due_date: date, today: date) -> NotificationKind:
    return (
        NotificationKind.overdue
        if today > due_date
        else NotificationKind.reminder
    )


def enqueue_for_occurrence(
    db: Session,
    occurrence: PaymentOccurrence,
    payment: RecurringPayment,
    *,
    today: date,
    channels: list[NotificationChannel] | None = None,
) -> int:
    """Create outbox rows for an occurrence when the reminder rule applies."""
    if not payment.is_active or occurrence.is_paid:
        return 0
    if not should_notify_reminder(
        is_paid=occurrence.is_paid,
        due_date=occurrence.due_date,
        today=today,
        days_before=settings.REMINDER_DAYS_BEFORE,
    ):
        return 0

    kind = kind_for(occurrence.due_date, today)
    if channels is None:
        channels = []
        if settings.telegram_enabled:
            channels.append(NotificationChannel.telegram)
        if settings.smtp_enabled:
            channels.append(NotificationChannel.email)

    created = 0
    for channel in channels:
        key = f"occ:{occurrence.id}:{channel.value}:{kind.value}"
        stmt = (
            pg_insert(NotificationLog)
            .values(
                occurrence_id=occurrence.id,
                channel=channel,
                kind=kind,
                status=DeliveryStatus.pending,
                idempotency_key=key,
                attempts=0,
            )
            .on_conflict_do_nothing(constraint="uq_notification_idempotency")
            .returning(NotificationLog.id)
        )
        # RETURNING yields rows only for inserts actually performed, which is a
        # reliable signal (psycopg reports rowcount as -1 for ON CONFLICT).
        created += len(db.execute(stmt).fetchall())
    db.flush()
    return created


def scan_and_enqueue(db: Session, today: date | None = None) -> int:
    """Scan all unpaid occurrences of active payments and enqueue reminders."""
    if today is None:
        today = local_today(settings.tz)

    rows = db.execute(
        select(PaymentOccurrence, RecurringPayment)
        .join(RecurringPayment, PaymentOccurrence.recurring_payment_id == RecurringPayment.id)
        .where(
            PaymentOccurrence.is_paid.is_(False),
            RecurringPayment.is_active.is_(True),
        )
    ).all()

    total = 0
    for occurrence, payment in rows:
        total += enqueue_for_occurrence(db, occurrence, payment, today=today)
    return total


def claim_pending(
    db: Session, *, limit: int = 50, now: datetime | None = None
) -> list[NotificationLog]:
    """Atomically claim pending outbox rows for delivery.

    ``FOR UPDATE SKIP LOCKED`` makes concurrent workers safe: each row is
    processed by exactly one worker at a time.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    stmt = (
        select(NotificationLog)
        .where(
            NotificationLog.status.in_([DeliveryStatus.pending, DeliveryStatus.failed]),
            NotificationLog.attempts < settings.WORKER_MAX_ATTEMPTS,
            (NotificationLog.next_attempt_at.is_(None))
            | (NotificationLog.next_attempt_at <= now),
        )
        .order_by(NotificationLog.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    rows = list(db.scalars(stmt))
    for row in rows:
        row.locked_at = now
    db.flush()
    return rows


def mark_sent(db: Session, entry: NotificationLog, now: datetime | None = None) -> None:
    entry.status = DeliveryStatus.sent
    entry.sent_at = now or datetime.now(timezone.utc)
    entry.last_error = None
    entry.locked_at = None
    db.flush()


def mark_failed(
    db: Session, entry: NotificationLog, error: str, *, now: datetime | None = None
) -> None:
    now = now or datetime.now(timezone.utc)
    entry.attempts += 1
    entry.last_error = error[:500]
    entry.locked_at = None
    if entry.attempts >= settings.WORKER_MAX_ATTEMPTS:
        entry.status = DeliveryStatus.failed
        entry.next_attempt_at = None
    else:
        entry.status = DeliveryStatus.failed
        backoff = min(2 ** entry.attempts, 60) * 60
        entry.next_attempt_at = now + timedelta(seconds=backoff)
    db.flush()
