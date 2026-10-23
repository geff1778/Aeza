"""SQLAlchemy models for Invoice Keeper."""
from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    admin = "admin"
    user = "user"


class Currency(str, enum.Enum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class Recurrence(str, enum.Enum):
    monthly = "monthly"
    quarterly = "quarterly"
    yearly = "yearly"


class BudgetPeriod(str, enum.Enum):
    month = "month"
    year = "year"


class NotificationChannel(str, enum.Enum):
    telegram = "telegram"
    email = "email"


class NotificationKind(str, enum.Enum):
    reminder = "reminder"
    overdue = "overdue"


class DeliveryStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role, name="role"), nullable=False, default=Role.user)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_bootstrap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class RecurringPayment(Base):
    __tablename__ = "recurring_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_recurring_amount_positive"),
        CheckConstraint("anchor_day BETWEEN 1 AND 31", name="ck_recurring_anchor_day"),
        Index("ix_recurring_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[Currency] = mapped_column(Enum(Currency, name="currency"), nullable=False)
    recurrence: Mapped[Recurrence] = mapped_column(
        Enum(Recurrence, name="recurrence"), nullable=False, default=Recurrence.monthly
    )
    anchor_day: Mapped[int] = mapped_column(Integer, nullable=False)
    first_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    occurrences: Mapped[list["PaymentOccurrence"]] = relationship(
        back_populates="recurring_payment", cascade="save-update, merge"
    )


class PaymentOccurrence(Base):
    __tablename__ = "payment_occurrences"
    __table_args__ = (
        UniqueConstraint("recurring_payment_id", "due_date", name="uq_occurrence_period"),
        CheckConstraint("amount > 0", name="ck_occurrence_amount_positive"),
        Index("ix_occurrence_due_date", "due_date"),
        Index("ix_occurrence_paid_due", "is_paid", "due_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recurring_payment_id: Mapped[int] = mapped_column(
        ForeignKey("recurring_payments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[Currency] = mapped_column(Enum(Currency, name="currency"), nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    paid_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    paid_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    receipt_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    recurring_payment: Mapped[RecurringPayment] = relationship(back_populates="occurrences")
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="occurrence", cascade="all, delete-orphan"
    )

    @property
    def status(self) -> str:
        """Computed payment status. Single source of truth for the whole product."""
        from app.services.status import compute_status

        return compute_status(
            is_paid=self.is_paid, paid_at=self.paid_at, due_date=self.due_date
        )


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurrence_id: Mapped[int] = mapped_column(
        ForeignKey("payment_occurrences.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    occurrence: Mapped[PaymentOccurrence] = relationship(back_populates="attachments")


class NotificationLog(Base):
    __tablename__ = "notification_logs"
    __table_args__ = (
        UniqueConstraint(
            "occurrence_id", "channel", "kind", name="uq_notification_idempotency"
        ),
        Index("ix_notification_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurrence_id: Mapped[int] = mapped_column(
        ForeignKey("payment_occurrences.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel"), nullable=False
    )
    kind: Mapped[NotificationKind] = mapped_column(
        Enum(NotificationKind, name="notification_kind"), nullable=False
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, name="delivery_status"), nullable=False, default=DeliveryStatus.pending
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_created", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_label: Mapped[str] = mapped_column(String(120), nullable=False, default="system")
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("period_type", "period_key", "currency", name="uq_budget_scope"),
        CheckConstraint("limit_amount >= 0", name="ck_budget_limit_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_type: Mapped[BudgetPeriod] = mapped_column(
        Enum(BudgetPeriod, name="budget_period"), nullable=False
    )
    period_key: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[Currency] = mapped_column(Enum(Currency, name="currency"), nullable=False)
    limit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
