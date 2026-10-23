"""Idempotent synthetic demo data for Invoice Keeper.

Safe to run repeatedly: payments are matched by title and periods are protected
by the (recurring_payment_id, due_date) unique constraint. Contains no secrets.
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import (
    Currency,
    PaymentOccurrence,
    Recurrence,
    RecurringPayment,
    Role,
    User,
)
from app.services import payments as payments_service
from app.services.dates import local_today
from app.services.generation import ensure_periods
from app.services.security import hash_password

DEMO_PAYMENTS = [
    {
        "title": "Аренда офиса",
        "description": "Ежемесячная аренда офисного помещения",
        "amount": Decimal("85000.00"),
        "currency": Currency.RUB,
        "anchor_day": 10,
        "recurrence": Recurrence.monthly,
    },
    {
        "title": "VPS Server",
        "description": "Виртуальный сервер для продакшена",
        "amount": Decimal("1500.00"),
        "currency": Currency.RUB,
        "anchor_day": 26,
        "recurrence": Recurrence.monthly,
    },
    {
        "title": "Figma Professional",
        "description": "Подписка на дизайн-инструмент",
        "amount": Decimal("45.00"),
        "currency": Currency.USD,
        "anchor_day": 5,
        "recurrence": Recurrence.monthly,
    },
    {
        "title": "Hetzner Cloud",
        "description": "Инфраструктура в Европе",
        "amount": Decimal("120.00"),
        "currency": Currency.EUR,
        "anchor_day": 15,
        "recurrence": Recurrence.monthly,
    },
    {
        "title": "Slack Business+",
        "description": "Корпоративный мессенджер",
        "amount": Decimal("12.50"),
        "currency": Currency.USD,
        "anchor_day": 1,
        "recurrence": Recurrence.monthly,
    },
]

# Demo credentials are synthetic and override-able via environment so the same
# script works for a shared demo box without baking a password into the repo.
DEMO_USER = {
    "username": os.getenv("DEMO_USERNAME", "demo_user"),
    "password": os.getenv("DEMO_PASSWORD", "DemoUser123!"),
    "email": os.getenv("DEMO_EMAIL", "demo_user@example.com"),
}


def _shift_month(base: date, months: int, anchor_day: int) -> date:
    from app.services.dates import add_months_anchored

    return add_months_anchored(base.year, base.month, months, anchor_day)


def ensure_demo_user(db) -> User:
    user = db.scalar(select(User).where(User.username == DEMO_USER["username"]))
    if user:
        return user
    user = User(
        username=DEMO_USER["username"],
        email=DEMO_USER["email"],
        password_hash=hash_password(DEMO_USER["password"]),
        role=Role.user,
        is_active=True,
    )
    db.add(user)
    db.commit()
    print(f"created demo user: {DEMO_USER['username']}")
    return user


def ensure_payment(db, admin: User, spec: dict, first_due: date) -> RecurringPayment:
    payment = db.scalar(
        select(RecurringPayment).where(RecurringPayment.title == spec["title"])
    )
    if payment:
        return payment
    payment = RecurringPayment(
        title=spec["title"],
        description=spec["description"],
        amount=spec["amount"],
        currency=spec["currency"],
        recurrence=spec["recurrence"],
        anchor_day=spec["anchor_day"],
        first_due_date=first_due,
        is_active=True,
        created_by_id=admin.id,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    ensure_periods(db, payment)
    db.commit()
    print(f"created payment: {payment.title}")
    return payment


def mark(db, admin: User, occurrence: PaymentOccurrence, paid_at: date) -> None:
    if occurrence.is_paid:
        return
    payments_service.mark_paid(db, actor=admin, occurrence=occurrence, paid_at=paid_at)


def main() -> int:
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.role == Role.admin).order_by(User.id))
        if admin is None:
            print("ERROR: bootstrap the admin first (scripts/bootstrap.py)", file=sys.stderr)
            return 1

        ensure_demo_user(db)
        today = local_today(settings.tz)

        for spec in DEMO_PAYMENTS:
            anchor = spec["anchor_day"]
            # Start three months in the past so history and overdue rows exist.
            first_due = _shift_month(today.replace(day=1), -3, anchor)
            payment = ensure_payment(db, admin, spec, first_due)

            periods = list(
                db.scalars(
                    select(PaymentOccurrence)
                    .where(PaymentOccurrence.recurring_payment_id == payment.id)
                    .order_by(PaymentOccurrence.due_date)
                )
            )
            for occurrence in periods:
                if occurrence.due_date > today:
                    continue
                if occurrence.due_date <= today - timedelta(days=45):
                    # Fully paid history, one of them paid late on purpose.
                    late = occurrence.due_date - timedelta(days=1)
                    mark(db, admin, occurrence, late + timedelta(days=2))
                elif occurrence.due_date <= today - timedelta(days=5):
                    # Deliberately left overdue for the demo.
                    continue
                else:
                    mark(db, admin, occurrence, occurrence.due_date)

        # A deliberately overdue period for "VPS Server" so the demo can show it.
        vps = db.scalar(select(RecurringPayment).where(RecurringPayment.title == "VPS Server"))
        if vps:
            overdue = db.scalar(
                select(PaymentOccurrence)
                .where(
                    PaymentOccurrence.recurring_payment_id == vps.id,
                    PaymentOccurrence.due_date < today,
                    PaymentOccurrence.is_paid.is_(False),
                )
                .order_by(PaymentOccurrence.due_date.desc())
            )
            if overdue is None:
                print("note: no overdue VPS period (already paid)")

        db.commit()
        print("demo data ready (idempotent)")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
