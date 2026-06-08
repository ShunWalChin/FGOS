from __future__ import annotations

import json
from typing import Any


def extract_inbound_message(payload: dict[str, Any]) -> dict[str, str] | None:
    """Extract the first text message from a Meta webhook payload.

    The structure intentionally stays defensive because Meta sends different
    shapes for Instagram, Messenger, WhatsApp, delivery receipts, and echoes.
    """

    try:
        entry = payload["entry"][0]
        change_or_message = (entry.get("changes") or entry.get("messaging") or [])[0]
    except (KeyError, IndexError, TypeError):
        return None

    value = change_or_message.get("value", change_or_message)
    message = value.get("message") or value.get("messages", [{}])[0]
    text = message.get("text")
    if isinstance(text, dict):
        text = text.get("body")
    if not text:
        return None

    sender_id = (
        value.get("sender", {}).get("id")
        or value.get("contacts", [{}])[0].get("wa_id")
        or message.get("from")
    )
    provider_message_id = message.get("id") or message.get("mid")
    if not sender_id:
        return None

    channel = value.get("messaging_product", "meta")
    session_key = json.dumps(
        {"channel": channel, "sender": sender_id},
        sort_keys=True,
    )
    return {
        "session_id": session_key,
        "channel": str(channel),
        "sender": str(sender_id),
        "text": str(text),
        "provider_message_id": str(provider_message_id or ""),
    }
