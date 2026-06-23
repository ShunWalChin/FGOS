from __future__ import annotations

import asyncio
import json
import logging
import socket
from typing import Any

from core_engine import repository as repo
from core_engine.bus import RedisStreamBus
from core_engine.db import create_session_factory, session_scope
from core_engine.events import Actor, EventEnvelope
from core_engine.providers.registry import get_provider
from core_engine.providers.social_base import PostAction, SocialProvider, plan_post_action
from core_engine.settings import Settings, get_settings

logger = logging.getLogger(__name__)


async def process_claimed_post(
    post: dict[str, Any],
    *,
    session,
    bus: RedisStreamBus,
    settings: Settings,
    provider: SocialProvider | None = None,
) -> PostAction:
    """Publish one claimed post and react to the outcome (docs/ARCHITECTURE.md §6).

    Returns the PostAction taken (handy for tests/observability).
    """

    platform = post["platform"]
    account_id = str(post["social_account_id"])
    post_id = str(post["id"])
    agency_id = post["agency_id"]
    payload = post["payload"] if isinstance(post["payload"], dict) else json.loads(post["payload"])

    provider = provider or get_provider(platform, settings)
    result = await provider.publish(token=post.get("token", ""), payload=payload)
    action = plan_post_action(result)

    # --- post disposition ---
    if action.post_disposition == "published":
        await repo.mark_social_post_published(
            session, post_id=post_id, platform_post_id=result.platform_post_id
        )
        # repost series (absorbed from Stackposts): re-enqueue the next occurrence
        repost_id = await repo.reschedule_repost(session, post_id=post_id)
        if repost_id:
            await _publish(bus, settings, EventEnvelope(
                event="social.post.reposted",
                agency_id=agency_id,
                actor=Actor(type="system", id="worker-social"),
                data={"post_id": post_id, "repost_id": repost_id, "platform": platform},
            ))
    else:
        await repo.mark_social_post_failed(
            session,
            post_id=post_id,
            error=result.error_message or action.outcome,
            max_attempts=settings.social_max_attempts,
            terminal=(action.post_disposition == "dead_letter"),
        )

    # --- account state transition ---
    disconnected: dict[str, Any] | None = None
    if action.account_status == "active":
        await repo.set_account_active(session, account_id=account_id)
    elif action.account_status == "rate_limited":
        await repo.set_account_rate_limited(
            session,
            account_id=account_id,
            cooldown_seconds=settings.social_rate_limit_cooldown_seconds,
        )
    elif action.account_status == "disconnected":
        disconnected = await repo.set_account_disconnected(session, account_id=account_id)

    # --- emit the primary event (router mirrors it to BI) ---
    await _publish(bus, settings, EventEnvelope(
        event=action.event,
        agency_id=agency_id,
        actor=Actor(type="system", id="worker-social"),
        data={
            "post_id": post_id,
            "social_account_id": account_id,
            "platform": platform,
            "platform_post_id": result.platform_post_id,
            "outcome": action.outcome,
            "error": result.error_message or None,
        },
    ))

    # --- on disconnect, create a re-OAuth task for the traffic team ---
    if disconnected is not None:
        task = await repo.create_reconnect_task(
            session,
            agency_id=str(agency_id),
            platform=platform,
            external_account_id=post.get("external_account_id", ""),
        )
        if task:
            await _publish(bus, settings, EventEnvelope(
                event="workspace.item.created",
                agency_id=agency_id,
                actor=Actor(type="system", id="worker-social"),
                data={
                    "item_id": task["item_id"],
                    "list_id": task["list_id"],
                    "title": task["title"],
                    "convert_to_deal": False,
                    "source": "social.account.disconnected",
                },
            ))

    return action


async def _publish(bus: RedisStreamBus, settings: Settings, event: EventEnvelope) -> None:
    await bus.publish(settings.stream_events, event)


async def run(settings: Settings | None = None, worker_id: str | None = None) -> None:
    settings = settings or get_settings()
    worker_id = worker_id or f"{socket.gethostname()}:social"
    session_factory = create_session_factory(settings.database_url)
    bus = RedisStreamBus.from_url(settings.redis_url)
    logger.info("social worker started", extra={"worker_id": worker_id})

    try:
        while True:
            async with session_scope(session_factory) as session:
                post = await repo.claim_next_social_post(
                    session,
                    worker_id=worker_id,
                    encryption_key=settings.token_encryption_key,
                )
            if not post:
                await asyncio.sleep(settings.social_worker_poll_seconds)
                continue

            try:
                async with session_scope(session_factory) as session:
                    await process_claimed_post(
                        post, session=session, bus=bus, settings=settings
                    )
            except Exception:
                logger.exception("social publish failed", extra={"post_id": str(post["id"])})
    finally:
        await bus.close()
