from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ErrorKind(str, Enum):
    """Taxonomy of social-publish failures — drives the worker's reaction.

    See docs/ARCHITECTURE.md §6 ("API Hell"). The reaction differs per kind:
    a rate limit pauses the *account*; an auth error disconnects it and asks the
    user to re-OAuth; an invalid payload is dead-lettered; network errors retry.
    """

    NONE = "none"
    RATE_LIMITED = "rate_limited"  # 429 — back off this account only
    AUTH = "auth"                  # 401/403 — token dead, needs re-OAuth
    INVALID = "invalid"            # 4xx that retrying won't fix — dead-letter
    NETWORK = "network"            # timeout / 5xx / connection — retry later


@dataclass(frozen=True)
class PublishResult:
    ok: bool
    platform_post_id: str | None = None
    error_kind: ErrorKind = ErrorKind.NONE
    error_message: str = ""

    @classmethod
    def success(cls, platform_post_id: str) -> "PublishResult":
        return cls(ok=True, platform_post_id=platform_post_id)

    @classmethod
    def failure(cls, kind: ErrorKind, message: str = "") -> "PublishResult":
        return cls(ok=False, error_kind=kind, error_message=message[:500])


@dataclass(frozen=True)
class PostAction:
    """The decision derived from a PublishResult — pure data, no I/O.

    The worker turns this into DB writes + events. Keeping it pure makes every
    branch of the "API Hell" reaction unit-testable without a database.
    """

    outcome: str           # published | rate_limited | auth | invalid | network
    account_status: str    # active | rate_limited | disconnected | unchanged
    post_disposition: str  # published | backoff | dead_letter
    event: str             # the event to emit on the bus


def plan_post_action(result: PublishResult) -> PostAction:
    if result.ok:
        return PostAction("published", "active", "published", "social.post.published")

    kind = result.error_kind
    if kind == ErrorKind.RATE_LIMITED:
        # pause the account only — the other 29 keep publishing
        return PostAction("rate_limited", "rate_limited", "backoff", "social.account.rate_limited")
    if kind == ErrorKind.AUTH:
        # token dead: disconnect account, ask user to re-OAuth; post waits
        return PostAction("auth", "disconnected", "backoff", "social.account.disconnected")
    if kind == ErrorKind.INVALID:
        # retrying won't fix it — dead-letter the post
        return PostAction("invalid", "unchanged", "dead_letter", "social.post.failed")
    # NETWORK / 5xx / timeout — retry with backoff
    return PostAction("network", "unchanged", "backoff", "social.post.failed")


def classify_status(status: int | None) -> ErrorKind:
    """Map an HTTP status (or None for a transport error) to an ErrorKind."""

    if status is None:
        return ErrorKind.NETWORK
    if status == 429:
        return ErrorKind.RATE_LIMITED
    if status in (401, 403):
        return ErrorKind.AUTH
    if 400 <= status < 500:
        return ErrorKind.INVALID
    if status >= 500:
        return ErrorKind.NETWORK
    return ErrorKind.NONE


class SocialProvider:
    """Provider boundary. Real platform adapters subclass this.

    Keeping publishing behind one narrow method makes rate-limit handling,
    token refresh and error classification testable per platform/account
    without touching the worker loop.
    """

    platform: str = "base"

    async def publish(self, *, token: str, payload: dict[str, Any]) -> PublishResult:
        raise NotImplementedError


class DryRunProvider(SocialProvider):
    """Default provider for local/dev. Pretends to publish and returns a
    synthetic platform_post_id. No network calls — safe for tests and offline."""

    def __init__(self, platform: str) -> None:
        self.platform = platform

    async def publish(self, *, token: str, payload: dict[str, Any]) -> PublishResult:
        import hashlib

        seed = f"{self.platform}:{payload.get('caption', '')}:{payload.get('scheduled_at', '')}"
        synthetic_id = "dry_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
        return PublishResult.success(synthetic_id)
