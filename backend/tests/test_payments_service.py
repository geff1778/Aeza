"""Unit tests for payment services: independence of periods, history retention."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Currency, PaymentOccurrence, Recurrence, RecurringPayment
from app.services import payments as svc
from app.services.generation import ensure_periods


def _payment(db, admin, **overrides) -> RecurringPayment:
    defaults = dict(
        actor=admin,
        title="Rent",
        amount=Decimal("1000.00"),
        currency=Currency.RUB,
        first_due_date=date.today(),
        recurrence=Recurrence.monthly,
        anchor_day=date.today().day,
    )
    defaults.update(overrides)
    return svc.create_recurring_payment(db, **defaults)


def test_create_payment_creates_first_period(db, admin_user):
    payment = _payment(db, admin_user)
    occurrences = list(
        db.scalars(
            select(PaymentOccurrence).where(PaymentOccurrence.recurring_payment_id == payment.id)
        )
    )
    assert len(occurrences) >= 1
    assert occurrences[0].due_date == payment.first_due_date
    assert occurrences[0].is_paid is False


def test_amount_and_currency_validation(db, admin_user):
    with pytest.raises(svc.DomainError):
        _payment(db, admin_user, amount=Decimal("0"))
    with pytest.raises(svc.DomainError):
        _payment(db, admin_user, amount=Decimal("-5"))
    with pytest.raises(svc.DomainError):
        _payment(db, admin_user, anchor_day=0)
    with pytest.raises(svc.DomainError):
        _payment(db, admin_user, anchor_day=32)


def test_generation_is_idempotent(db, admin_user):
    payment = _payment(db, admin_user)
    first_count = len(
        list(db.scalars(select(PaymentOccurrence).where(PaymentOccurrence.recurring_payment_id == payment.id)))
    )
    ensure_periods(db, payment)
    ensure_periods(db, payment)
    db.commit()
    second_count = len(
        list(db.scalars(select(PaymentOccurrence).where(PaymentOccurrence.recurring_payment_id == payment.id)))
    )
    assert first_count == second_count


def test_periods_are_independent(db, admin_user):
    """Paying October must not pay November or December."""
    today = date.today()
    payment = _payment(db, admin_user, first_due_date=today - timedelta(days=60), anchor_day=(today - timedelta(days=60)).day)
    occurrences = list(
        db.scalars(
            select(PaymentOccurrence)
            .where(PaymentOccurrence.recurring_payment_id == payment.id)
            .order_by(PaymentOccurrence.due_date)
        )
    )
    assert len(occurrences) >= 3
    first, second, third = occurrences[0], occurrences[1], occurrences[2]
    svc.mark_paid(db, actor=admin_user, occurrence=first, paid_at=first.due_date)
    db.refresh(second)
    db.refresh(third)
    assert first.is_paid is True
    assert second.is_paid is False
    assert third.is_paid is False


def test_overdue_period_does_not_block_future_generation(db, admin_user):
    today = date.today()
    payment = _payment(db, admin_user, first_due_date=today - timedelta(days=90), anchor_day=(today - timedelta(days=90)).day)
    occurrences = list(
        db.scalars(
            select(PaymentOccurrence)
            .where(PaymentOccurrence.recurring_payment_id == payment.id)
            .order_by(PaymentOccurrence.due_date)
        )
    )
    overdue = [o for o in occurrences if o.due_date < today and not o.is_paid]
    future = [o for o in occurrences if o.due_date > today]
    assert overdue, "expected an unpaid overdue period"
    assert future, "expected future periods despite the overdue one"


def test_correct_paid_date_recalculates_status(db, admin_user):
    today = date.today()
    payment = _payment(db, admin_user, first_due_date=today - timedelta(days=5), anchor_day=(today - timedelta(days=5)).day)
    occurrence = db.scalar(
        select(PaymentOccurrence).where(PaymentOccurrence.recurring_payment_id == payment.id).order_by(PaymentOccurrence.due_date)
    )
    svc.mark_paid(db, actor=admin_user, occurrence=occurrence, paid_at=today)
    assert occurrence.status == "paid_late"

    svc.update_occurrence(db, actor=admin_user, occurrence=occurrence, paid_at=occurrence.due_date - timedelta(days=1))
    assert occurrence.status == "paid_on_time"
    # The due date must not have moved.
    assert occurrence.due_date == payment.first_due_date


def test_unmark_restores_overdue(db, admin_user):
    today = date.today()
    payment = _payment(db, admin_user, first_due_date=today - timedelta(days=7), anchor_day=(today - timedelta(days=7)).day)
    occurrence = db.scalar(
        select(PaymentOccurrence).where(PaymentOccurrence.recurring_payment_id == payment.id).order_by(PaymentOccurrence.due_date)
    )
    svc.mark_paid(db, actor=admin_user, occurrence=occurrence)
    assert occurrence.is_paid is True
    svc.unmark_paid(db, actor=admin_user, occurrence=occurrence)
    assert occurrence.is_paid is False
    assert occurrence.paid_at is None
    assert occurrence.status == "overdue"


def test_unmark_future_period_becomes_pending(db, admin_user):
    today = date.today()
    future = today + timedelta(days=40)
    payment = _payment(db, admin_user, first_due_date=future, anchor_day=future.day)
    occurrence = db.scalar(
        select(PaymentOccurrence).where(PaymentOccurrence.recurring_payment_id == payment.id).order_by(PaymentOccurrence.due_date)
    )
    svc.mark_paid(db, actor=admin_user, occurrence=occurrence, paid_at=today)
    svc.unmark_paid(db, actor=admin_user, occurrence=occurrence)
    assert occurrence.status in ("pending", "due_soon")


def test_mark_paid_is_idempotent(db, admin_user):
    today = date.today()
    payment = _payment(db, admin_user, first_due_date=today, anchor_day=today.day)
    occurrence = db.scalar(
        select(PaymentOccurrence).where(PaymentOccurrence.recurring_payment_id == payment.id).order_by(PaymentOccurrence.due_date)
    )
    svc.mark_paid(db, actor=admin_user, occurrence=occurrence, paid_at=today)
    first_paid_at = occurrence.paid_at
    svc.mark_paid(db, actor=admin_user, occurrence=occurrence, paid_at=today)
    assert occurrence.paid_at == first_paid_at


def test_deactivate_stops_generation_and_keeps_history(db, admin_user):
    today = date.today()
    payment = _payment(db, admin_user, first_due_date=today - timedelta(days=30), anchor_day=(today - timedelta(days=30)).day)
    before = list(
        db.scalars(select(PaymentOccurrence).where(PaymentOccurrence.recurring_payment_id == payment.id))
    )
    assert before
    svc.deactivate_recurring_payment(db, actor=admin_user, payment=payment)
    assert payment.is_active is False

    created = ensure_periods(db, payment)
    db.commit()
    after = list(
        db.scalars(select(PaymentOccurrence).where(PaymentOccurrence.recurring_payment_id == payment.id))
    )
    assert created == 0
    assert len(after) == len(before), "history must be preserved after completion"


def test_audit_records_are_written(db, admin_user):
    from app.models import AuditLog

    payment = _payment(db, admin_user)
    logs = list(db.scalars(select(AuditLog)))
    assert any(log.action == "recurring_payment.created" for log in logs)

    occurrence = db.scalar(
        select(PaymentOccurrence).where(PaymentOccurrence.recurring_payment_id == payment.id)
    )
    svc.mark_paid(db, actor=admin_user, occurrence=occurrence)
    logs = list(db.scalars(select(AuditLog)))
    assert any(log.action == "payment_occurrence.marked_paid" for log in logs)
