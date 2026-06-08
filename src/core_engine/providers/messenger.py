from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core_engine.settings import Settings


@dataclass(frozen=True)
class SendResult:
    ok: bool
    provider_msg_id: str | None = None
    error: str = ""


class MessengerProvider:
    """Boundary for sending an outbound message back to the channel
    (WhatsApp/Instagram/Messenger via the Meta Send API). Real adapters subclass."""

    channel: str = "base"

    async def send(self, *, to: str, text: str) -> SendResult:
        raise NotImplementedError


@dataclass
class DryRunMessenger(MessengerProvider):
    """No-network sender for dev/tests: returns a synthetic provider_msg_id."""

    channel: str = "meta"

    async def send(self, *, to: str, text: str) -> SendResult:
        import hashlib

        mid = "dry_out_" + hashlib.sha1(f"{to}:{text}".encode("utf-8")).hexdigest()[:16]
        return SendResult(ok=True, provider_msg_id=mid)


def get_messenger(channel: str, settings: "Settings") -> MessengerProvider:
    """Dry-run unless MESSAGING_LIVE=true. Live Meta Send API adapter plugs in
    here, reusing the OAuth tokens stored per account (Module B)."""

    if not settings.messaging_live:
        return DryRunMessenger(channel=channel)
    # Live Meta Send API adapter plugs in here.
    return DryRunMessenger(channel=channel)
