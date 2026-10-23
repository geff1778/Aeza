"""SMTP email transport. Never blocks application start-up when unconfigured."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings
from app.services.telegram import DeliveryResult


def send_email(
    subject: str,
    body: str,
    *,
    to: str | None = None,
    transport=None,
) -> DeliveryResult:
    if not settings.smtp_enabled:
        return DeliveryResult(ok=False, error="smtp_not_configured")

    recipient = to or settings.SMTP_TO or settings.SMTP_USERNAME
    if not recipient:
        return DeliveryResult(ok=False, error="smtp_recipient_missing")

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    if transport is not None:  # injectable transport for tests
        try:
            transport.send_message(message)
            return DeliveryResult(ok=True)
        except Exception as exc:  # noqa: BLE001 - record any transport failure
            return DeliveryResult(ok=False, error=f"transport_error: {exc.__class__.__name__}")

    try:
        if settings.SMTP_USE_TLS:
            context = ssl.create_default_context()
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
                server.starttls(context=context)
                if settings.SMTP_USERNAME:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(message)
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
                if settings.SMTP_USERNAME:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(message)
        return DeliveryResult(ok=True)
    except Exception as exc:  # noqa: BLE001 - network/auth failures are retryable
        return DeliveryResult(ok=False, error=f"smtp_error: {exc.__class__.__name__}")
