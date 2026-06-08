from __future__ import annotations

import asyncio
import time

from sqlalchemy.ext.asyncio import AsyncSession

from core_engine.bus import RedisStreamBus
from core_engine.events import EventEnvelope
from core_engine.providers.meta import extract_inbound_message
from core_engine.settings import Settings, get_settings
from core_engine.workers.runtime import run_stream_worker

DEBOUNCE_ZSET = "debounce:messaging"


async def handle_meta_message(
    event: EventEnvelope,
    _session: AsyncSession,
    bus: RedisStreamBus,
    settings: Settings,
) -> None:
    if event.event != "webhook.meta.received":
        return

    inbound = extract_inbound_message(event.data.get("payload", {}))
    if not inbound:
        return

    session_id = inbound["session_id"]
    await bus.add_to_debounce(
        f"buf:messaging:{session_id}",
        inbound["text"],
        ttl_seconds=60,
    )
    await bus.redis.zadd(
        DEBOUNCE_ZSET,
        {session_id: time.time() + settings.messaging_debounce_seconds},
    )


async def flush_due_buffers(
    bus: RedisStreamBus,
    settings: Settings | None = None,
) -> list[dict[str, str]]:
    settings = settings or get_settings()
    now = time.time()
    due_session_ids = await bus.redis.zrangebyscore(DEBOUNCE_ZSET, min=0, max=now)
    flushed: list[dict[str, str]] = []

    for raw_session_id in due_session_ids:
        session_id = (
            raw_session_id.decode("utf-8")
            if isinstance(raw_session_id, bytes)
            else str(raw_session_id)
        )
        await bus.redis.zrem(DEBOUNCE_ZSET, session_id)
        parts = await bus.drain_list(f"buf:messaging:{session_id}")
        if not parts:
            continue

        consolidated = "\n".join(parts)
        reply_event = EventEnvelope(
            event="messaging.session.buffered",
            agency_id=settings.default_agency_id,
            actor={"type": "system", "id": "worker-messaging"},
            data={"session_id": session_id, "text": consolidated},
        )
        await bus.publish(settings.stream_events, reply_event)
        flushed.append({"session_id": session_id, "text": consolidated})

    return flushed


async def run_message_buffer_flusher(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    bus = RedisStreamBus.from_url(settings.redis_url)
    try:
        while True:
            await flush_due_buffers(bus, settings)
            await asyncio.sleep(0.5)
    finally:
        await bus.close()


async def run(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    await run_stream_worker(
        stream=settings.stream_webhooks_meta,
        handler=handle_meta_message,
        settings=settings,
    )
