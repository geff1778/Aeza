"""Notification rules, outbox idempotency, retries and callback handling."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import (
    Currency,
    DeliveryStatus,
    NotificationChannel,
    NotificationKind,
    NotificationLog,
    PaymentOccurrence,
    Recurrence,
    RecurringPayment,
)
from app.services import dispatcher, notifications, telegram_callbacks
from app.services.dates import local_today
from app.services.messages import build_message


class FakeTelegram:
    """Mock transport: records calls, can be told to fail."""

    def __init__(self, fail_times: int = 0) -> None:
        self.calls: list[dict] = []
        self.fail_times = fail_times

    def post(self, url, json=None, **kwargs):  # noqa: A002 - httpx-compatible signature
        self.calls.append({"url": url, "json": json})

        class _Resp:
            status_code = 200
            text = ""

            def __init__(self, ok: bool, description: str = "") -> None:
                self._ok = ok
                self._description = description

            def json(self):
                return {"ok": self._ok, "description": self._description}

        if self.fail_times > 0:
            self.fail_times -= 1
            return _Resp(False, "simulated failure")
        return _Resp(True)

    def close(self):
        pass


def _payment(db, admin, *, due_offset_days: int, amount="1500.00", currency=Currency.RUB):
    due = local_today(settings_tz()) + timedelta(days=due_offset_days)
    payment = RecurringPayment(
        title="VPS Server",
        amount=Decimal(amount),
        currency=currency,
        recurrence=Recurrence.monthly,
        anchor_day=due.day,
        first_due_date=due,
        is_active=True,
        created_by_id=admin.id,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    from app.services.generation import ensure_periods

    ensure_periods(db, payment)
    db.commit()
    occurrence = db.scalar(
        select(PaymentOccurrence)
        .where(PaymentOccurrence.recurring_payment_id == payment.id)
        .order_by(PaymentOccurrence.due_date)
    )
    return payment, occurrence


def settings_tz():
    from app.config import settings

    return settings.tz


@pytest.fixture(autouse=True)
def _enable_telegram(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "12345")
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(settings, "SMTP_FROM", "")


def test_message_contains_title_amount_due_and_days(db, admin_user):
    payment, occurrence = _payment(db, admin_user, due_offset_days=3)
    today = local_today(settings_tz())
    html, plain = build_message(
        occurrence, payment, kind=NotificationKind.reminder, today=today
    )
    assert "VPS Server" in html
    assert "1 500 RUB" in html
    assert "Осталось 3 дн." in html
    assert "ожидает оплаты" in html


def test_reminder_is_enqueued_three_days_before(db, admin_user):
    payment, occurrence = _payment(db, admin_user, due_offset_days=3)
    created = notifications.enqueue_for_occurrence(
        db, occurrence, payment, today=local_today(settings_tz())
    )
    db.commit()
    assert created == 1
    entry = db.scalar(select(NotificationLog))
    assert entry.kind == NotificationKind.reminder
    assert entry.channel == NotificationChannel.telegram
    assert entry.idempotency_key == f"occ:{occurrence.id}:telegram:reminder"


def test_immediate_reminder_for_close_due_date(db, admin_user):
    """Created with less than the reminder window left -> notify immediately."""
    payment, occurrence = _payment(db, admin_user, due_offset_days=1)
    created = notifications.enqueue_for_occurrence(
        db, occurrence, payment, today=local_today(settings_tz())
    )
    db.commit()
    assert created == 1


def test_no_reminder_beyond_window(db, admin_user):
    payment, occurrence = _payment(db, admin_user, due_offset_days=30)
    created = notifications.enqueue_for_occurrence(
        db, occurrence, payment, today=local_today(settings_tz())
    )
    assert created == 0


def test_no_reminder_for_paid_period(db, admin_user):
    from app.services import payments as payments_service

    payment, occurrence = _payment(db, admin_user, due_offset_days=2)
    payments_service.mark_paid(db, actor=admin_user, occurrence=occurrence)
    created = notifications.enqueue_for_occurrence(
        db, occurrence, payment, today=local_today(settings_tz())
    )
    assert created == 0


def test_no_reminder_after_payment_completed(db, admin_user):
    from app.services import payments as payments_service

    payment, occurrence = _payment(db, admin_user, due_offset_days=2)
    payments_service.deactivate_recurring_payment(db, actor=admin_user, payment=payment)
    created = notifications.enqueue_for_occurrence(
        db, occurrence, payment, today=local_today(settings_tz())
    )
    assert created == 0


def test_worker_rerun_does_not_duplicate(db, admin_user):
    _payment(db, admin_user, due_offset_days=3)
    first = notifications.scan_and_enqueue(db)
    db.commit()
    second = notifications.scan_and_enqueue(db)
    db.commit()
    third = notifications.scan_and_enqueue(db)
    db.commit()
    assert first == 1
    assert second == 0
    assert third == 0
    assert len(list(db.scalars(select(NotificationLog)))) == 1


def test_overdue_kind_is_used_after_deadline(db, admin_user):
    payment, occurrence = _payment(db, admin_user, due_offset_days=-2)
    notifications.enqueue_for_occurrence(db, occurrence, payment, today=local_today(settings_tz()))
    db.commit()
    entry = db.scalar(select(NotificationLog))
    assert entry.kind == NotificationKind.overdue


def test_delivery_marks_sent_and_records_audit(db, admin_user):
    payment, occurrence = _payment(db, admin_user, due_offset_days=2)
    notifications.enqueue_for_occurrence(db, occurrence, payment, today=local_today(settings_tz()))
    db.commit()
    entry = notifications.claim_pending(db)
    db.commit()
    assert len(entry) == 1

    transport = FakeTelegram()
    assert dispatcher.deliver_entry(db, entry[0], transport=transport) is True
    db.refresh(entry[0])
    assert entry[0].status == DeliveryStatus.sent
    assert entry[0].sent_at is not None

    sent_payload = transport.calls[0]["json"]
    assert "VPS Server" in sent_payload["text"]
    assert "callback_data" in str(sent_payload["reply_markup"])
    assert f"paid:{occurrence.id}" in str(sent_payload["reply_markup"])


def test_failure_is_recorded_and_retried(db, admin_user):
    payment, occurrence = _payment(db, admin_user, due_offset_days=2)
    notifications.enqueue_for_occurrence(db, occurrence, payment, today=local_today(settings_tz()))
    db.commit()
    entry = notifications.claim_pending(db)[0]
    db.commit()

    transport = FakeTelegram(fail_times=1)
    assert dispatcher.deliver_entry(db, entry, transport=transport) is False
    db.refresh(entry)
    assert entry.status == DeliveryStatus.failed
    assert entry.attempts == 1
    assert entry.last_error
    assert entry.next_attempt_at is not None

    # A later cycle retries and succeeds.
    entry.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    retry = notifications.claim_pending(db)
    assert len(retry) == 1
    assert dispatcher.deliver_entry(db, retry[0], transport=transport) is True
    db.refresh(entry)
    assert entry.status == DeliveryStatus.sent
    assert entry.attempts == 1


def test_max_attempts_stops_retrying(db, admin_user, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "WORKER_MAX_ATTEMPTS", 2)
    payment, occurrence = _payment(db, admin_user, due_offset_days=2)
    notifications.enqueue_for_occurrence(db, occurrence, payment, today=local_today(settings_tz()))
    db.commit()

    transport = FakeTelegram(fail_times=99)
    for _ in range(3):
        entries = notifications.claim_pending(db)
        db.commit()
        for entry in entries:
            dispatcher.deliver_entry(db, entry, transport=transport)
        # make retries immediately eligible again
        for entry in db.scalars(select(NotificationLog)):
            entry.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

    entry = db.scalar(select(NotificationLog))
    assert entry.attempts >= 2
    assert notifications.claim_pending(db) == []


def test_no_token_means_no_simulated_success(db, admin_user, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    payment, occurrence = _payment(db, admin_user, due_offset_days=2)
    created = notifications.enqueue_for_occurrence(
        db, occurrence, payment, today=local_today(settings_tz())
    )
    db.commit()
    # Without a token no telegram channel is even considered.
    assert created == 0
    assert db.scalar(select(NotificationLog)) is None


def test_callback_marks_paid_and_is_idempotent(db, admin_user):
    payment, occurrence = _payment(db, admin_user, due_offset_days=-3)
    answer = telegram_callbacks.handle_paid_callback(db, f"paid:{occurrence.id}")
    db.refresh(occurrence)
    assert occurrence.is_paid is True
    assert occurrence.paid_at == local_today(settings_tz())
    assert occurrence.status == "paid_late"
    assert "просрочкой" in answer

    second = telegram_callbacks.handle_paid_callback(db, f"paid:{occurrence.id}")
    assert second == "Уже отмечено как оплачено"
    assert len(list(db.scalars(select(PaymentOccurrence).where(PaymentOccurrence.id == occurrence.id)))) == 1


def test_callback_rejects_bad_payload(db, admin_user):
    assert telegram_callbacks.handle_paid_callback(db, "drop table") == "Неизвестное действие"
    assert telegram_callbacks.handle_paid_callback(db, "paid:abc") == "Некорректный идентификатор платежа"
    assert telegram_callbacks.handle_paid_callback(db, "paid:999999") == "Период не найден"


def test_callback_rejects_completed_payment(db, admin_user):
    from app.services import payments as payments_service

    payment, occurrence = _payment(db, admin_user, due_offset_days=-3)
    payments_service.deactivate_recurring_payment(db, actor=admin_user, payment=payment)
    answer = telegram_callbacks.handle_paid_callback(db, f"paid:{occurrence.id}")
    db.refresh(occurrence)
    assert occurrence.is_paid is False
    assert answer == "Регулярный платёж завершён"


def test_allowed_user_restriction(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "TELEGRAM_ALLOWED_USER_IDS", "111,222")
    assert telegram_callbacks.is_allowed_user(111, "111") is True
    assert telegram_callbacks.is_allowed_user(999, "999") is False
    monkeypatch.setattr(settings, "TELEGRAM_ALLOWED_USER_IDS", "")
    assert telegram_callbacks.is_allowed_user(999, "999") is True


def test_email_transport_records_failure_without_smtp(monkeypatch):
    from app.config import settings
    from app.services import email as email_transport

    monkeypatch.setattr(settings, "SMTP_HOST", "")
    result = email_transport.send_email("subject", "body")
    assert result.ok is False
    assert result.error == "smtp_not_configured"


def test_email_uses_injected_transport(monkeypatch):
    from app.config import settings
    from app.services import email as email_transport

    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_FROM", "invoice@example.com")
    monkeypatch.setattr(settings, "SMTP_TO", "ops@example.com")

    sent = []

    class FakeSMTP:
        def send_message(self, message):
            sent.append(message)

    result = email_transport.send_email("Тема", "Тело", transport=FakeSMTP())
    assert result.ok is True
    assert len(sent) == 1
    assert sent[0]["To"] == "ops@example.com"
    assert sent[0]["Subject"] == "Тема"


def test_no_configured_channel_enqueues_nothing_even_when_overdue(db, admin_user, monkeypatch):
    """With no channel configured, the outbox stays empty on purpose.

    This is the production default: an overdue period exists, but no Telegram
    token and no SMTP host means there is nobody to notify. The product must
    stay silent rather than record a fake delivery.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(settings, "SMTP_FROM", "")

    _payment(db, admin_user, due_offset_days=-5)  # overdue
    _payment(db, admin_user, due_offset_days=1)  # due tomorrow

    enqueued = notifications.scan_and_enqueue(db)
    db.commit()

    assert enqueued == 0
    assert db.scalar(select(NotificationLog)) is None


def test_configured_channel_enqueues_overdue_notice(db, admin_user):
    """The same scan does enqueue once a channel exists, so silence above is
    caused by the missing channel and not by a broken scan."""
    _payment(db, admin_user, due_offset_days=-5)
    enqueued = notifications.scan_and_enqueue(db)
    db.commit()
    assert enqueued == 1
    entry = db.scalar(select(NotificationLog))
    assert entry.channel == NotificationChannel.telegram
    assert entry.kind == NotificationKind.overdue
