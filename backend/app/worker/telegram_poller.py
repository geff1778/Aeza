"""Long-polling for Telegram callback queries (the inline "Оплачено" button).

Long polling avoids requiring a public HTTPS endpoint, which is the right
trade-off for a self-hosted deployment behind a private network.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.db import SessionLocal
from app.services import telegram, telegram_callbacks

log = logging.getLogger("invoice.worker.telegram")

_state = {"offset": 0}


def _get_updates(client: httpx.Client) -> list[dict]:
    resp = client.post(
        f"{settings.TELEGRAM_API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates",
        json={"offset": _state["offset"], "timeout": 0, "allowed_updates": ["callback_query"]},
    )
    if resp.status_code != 200:
        return []
    body = resp.json()
    if not body.get("ok"):
        return []
    return body.get("result", [])


def poll_telegram_callbacks(client: httpx.Client | None = None) -> int:
    """Process pending callback queries. Returns the number handled."""
    if not settings.telegram_enabled:
        return 0

    owns_client = client is None
    client = client or httpx.Client(timeout=20)
    handled = 0
    try:
        for update in _get_updates(client):
            _state["offset"] = update.get("update_id", _state["offset"]) + 1
            callback = update.get("callback_query")
            if not callback:
                continue

            from_user = callback.get("from") or {}
            message = callback.get("message") or {}
            chat_id = (message.get("chat") or {}).get("id")
            if not telegram_callbacks.is_allowed_user(from_user.get("id"), chat_id):
                telegram.answer_callback_query(callback["id"], "Нет доступа", client=client)
                continue

            with SessionLocal() as db:
                answer = telegram_callbacks.handle_paid_callback(db, callback.get("data", ""))

            telegram.answer_callback_query(callback["id"], answer, client=client)
            if message.get("message_id") and chat_id is not None:
                telegram.edit_message_text(
                    str(chat_id), message["message_id"], f"✅ {answer}", client=client
                )
            handled += 1
            log.info("handled telegram callback: %s", answer)
    finally:
        if owns_client:
            client.close()
    return handled
