from __future__ import annotations

import asyncio
import logging
import socket

from core_engine.db import create_session_factory, session_scope
from core_engine.repository import (
    claim_next_social_post,
    mark_social_post_failed,
    mark_social_post_published,
)
from core_engine.settings import Settings, get_settings

logger = logging.getLogger(__name__)


async def publish_post_to_platform(post: dict) -> None:
    """Provider boundary.

    Real platform adapters live behind this function. Keeping it narrow makes
    rate-limit handling and OAuth refresh policy testable per platform/account.
    """

    logger.info("dry provider publish", extra={"post_id": str(post["id"])})


async def run(settings: Settings | None = None, worker_id: str | None = None) -> None:
    settings = settings or get_settings()
    worker_id = worker_id or f"{socket.gethostname()}:social"
    session_factory = create_session_factory(settings.database_url)

    while True:
        async with session_scope(session_factory) as session:
            post = await claim_next_social_post(session, worker_id=worker_id)
        if not post:
            await asyncio.sleep(settings.social_worker_poll_seconds)
            continue

        async with session_scope(session_factory) as session:
            try:
                await publish_post_to_platform(post)
                await mark_social_post_published(session, post_id=str(post["id"]))
            except Exception as exc:
                await mark_social_post_failed(session, post_id=str(post["id"]), error=str(exc))
