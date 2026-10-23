"""Notification & period-generation worker.

Runs as its own process (never inside the API), so the scheduler exists exactly
once. Two responsibilities:

1. Materialise missing payment periods on a rolling horizon.
2. Scan for due reminders, enqueue them into the outbox and deliver them.

Both steps are idempotent, which is why re-running the worker after a restart is
safe: periods are protected by a unique constraint and notifications by an
idempotency key.
"""
from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import NotificationLog
from app.services import dispatcher, notifications
from app.services.dates import local_today
from app.services.generation import ensure_all_periods
from app.worker.telegram_poller import poll_telegram_callbacks

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s [worker] %(message)s"
)
log = logging.getLogger("invoice.worker")


def run_generation_cycle(db: Session) -> int:
    created = ensure_all_periods(db, local_today(settings.tz))
    db.commit()
    if created:
        log.info("materialised %s new payment period(s)", created)
    return created


def run_notification_cycle(db: Session) -> tuple[int, int]:
    enqueued = notifications.scan_and_enqueue(db)
    db.commit()

    sent = failed = 0
    entries: list[NotificationLog] = notifications.claim_pending(db)
    db.commit()
    for entry in entries:
        if dispatcher.deliver_entry(db, entry):
            sent += 1
        else:
            failed += 1
    if enqueued or sent or failed:
        log.info("notifications: enqueued=%s sent=%s failed=%s", enqueued, sent, failed)
    return sent, failed


def run_once() -> None:
    with SessionLocal() as db:
        run_generation_cycle(db)
        run_notification_cycle(db)


def main() -> None:
    log.info("worker started (interval=%ss, tz=%s)", settings.WORKER_INTERVAL_SECONDS, settings.APP_TIMEZONE)
    if not settings.telegram_enabled:
        log.warning(
            "Telegram is not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing): "
            "no Telegram reminders will be enqueued or sent, and nothing is simulated"
        )
    if not settings.smtp_enabled:
        log.warning(
            "SMTP is not configured (SMTP_HOST / SMTP_FROM missing): "
            "no email notifications will be enqueued or sent"
        )

    last_poll = 0.0
    while True:
        try:
            run_once()
        except Exception:  # noqa: BLE001 - the loop must survive transient DB errors
            log.exception("cycle failed")

        if settings.telegram_enabled:
            try:
                poll_telegram_callbacks()
            except Exception:  # noqa: BLE001
                log.exception("telegram poll failed")

        last_poll = time.monotonic()
        time.sleep(max(5, settings.WORKER_INTERVAL_SECONDS))


if __name__ == "__main__":
    main()
