from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from core_engine.bus import RedisStreamBus
from core_engine.db import create_session_factory, session_scope
from core_engine.events import EventEnvelope
from core_engine.repository import mark_event_started, record_event_failure
from core_engine.settings import Settings, get_settings

logger = logging.getLogger(__name__)

EventHandler = Callable[[EventEnvelope, AsyncSession, RedisStreamBus, Settings], Awaitable[None]]


async def run_stream_worker(
    *,
    stream: str,
    handler: EventHandler,
    settings: Settings | None = None,
    consumer_name: str | None = None,
    read_count: int = 10,
    worker_role: str = "default",
) -> None:
    settings = settings or get_settings()
    consumer_name = consumer_name or f"{socket.gethostname()}:{stream}"
    bus = RedisStreamBus.from_url(settings.redis_url)
    session_factory = create_session_factory(settings.database_url)

    await bus.ensure_group(stream, settings.worker_group)
    logger.info("worker started", extra={"stream": stream, "consumer": consumer_name})

    try:
        while True:
            messages = await bus.read_group(
                stream=stream,
                group=settings.worker_group,
                consumer=consumer_name,
                count=read_count,
            )
            if not messages:
                await asyncio.sleep(0)
                continue

            for message in messages:
                try:
                    async with session_scope(session_factory) as session:
                        is_new = await mark_event_started(
                            session, message.event, worker_role=worker_role
                        )
                        if not is_new:
                            pass
                        elif message.event.hops > settings.max_event_hops:
                            await record_event_failure(
                                session,
                                message.event,
                                reason="max_hops_exceeded",
                                detail=f"hops={message.event.hops}",
                            )
                        else:
                            await handler(message.event, session, bus, settings)

                    await bus.ack(message.stream, settings.worker_group, message.message_id)
                except Exception:
                    logger.exception(
                        "event processing failed",
                        extra={"stream": message.stream, "message_id": message.message_id},
                    )
    finally:
        await bus.close()
