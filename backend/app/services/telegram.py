"""Telegram Bot API transport.

Only ever called by the notification worker. Returns a delivery result instead
of raising so the worker can record failures in the outbox.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import settings


@dataclass
class DeliveryResult:
    ok: bool
    error: str | None = None


def _endpoint(method: str) -> str:
    return f"{settings.TELEGRAM_API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"


def send_message(
    text: str,
    *,
    reply_markup: dict | None = None,
    chat_id: str | None = None,
    client: httpx.Client | None = None,
) -> DeliveryResult:
    if not settings.telegram_enabled:
        return DeliveryResult(ok=False, error="telegram_not_configured")

    payload: dict = {
        "chat_id": chat_id or settings.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    owns_client = client is None
    client = client or httpx.Client(timeout=15)
    try:
        resp = client.post(_endpoint("sendMessage"), json=payload)
        if resp.status_code == 200:
            body = resp.json()
            if body.get("ok"):
                return DeliveryResult(ok=True)
            return DeliveryResult(ok=False, error=str(body.get("description", "telegram_error"))[:500])
        return DeliveryResult(ok=False, error=f"http_{resp.status_code}: {resp.text[:200]}")
    except httpx.HTTPError as exc:  # network failure -> retry later
        return DeliveryResult(ok=False, error=f"network_error: {exc.__class__.__name__}")
    finally:
        if owns_client:
            client.close()


def answer_callback_query(callback_query_id: str, text: str, client: httpx.Client | None = None) -> DeliveryResult:
    if not settings.TELEGRAM_BOT_TOKEN:
        return DeliveryResult(ok=False, error="telegram_not_configured")
    owns_client = client is None
    client = client or httpx.Client(timeout=15)
    try:
        resp = client.post(
            _endpoint("answerCallbackQuery"),
            json={"callback_query_id": callback_query_id, "text": text},
        )
        if resp.status_code == 200 and resp.json().get("ok"):
            return DeliveryResult(ok=True)
        return DeliveryResult(ok=False, error=resp.text[:200])
    except httpx.HTTPError as exc:
        return DeliveryResult(ok=False, error=f"network_error: {exc.__class__.__name__}")
    finally:
        if owns_client:
            client.close()


def edit_message_text(
    chat_id: str, message_id: int, text: str, client: httpx.Client | None = None
) -> DeliveryResult:
    if not settings.TELEGRAM_BOT_TOKEN:
        return DeliveryResult(ok=False, error="telegram_not_configured")
    owns_client = client is None
    client = client or httpx.Client(timeout=15)
    try:
        resp = client.post(
            _endpoint("editMessageText"),
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": []},
            },
        )
        if resp.status_code == 200 and resp.json().get("ok"):
            return DeliveryResult(ok=True)
        return DeliveryResult(ok=False, error=resp.text[:200])
    except httpx.HTTPError as exc:
        return DeliveryResult(ok=False, error=f"network_error: {exc.__class__.__name__}")
    finally:
        if owns_client:
            client.close()
