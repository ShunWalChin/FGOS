from __future__ import annotations

import asyncio
import json
import logging
import socket
import time

from core_engine.bus import RedisStreamBus
from core_engine.clickhouse_client import create_clickhouse_client
from core_engine.db import create_session_factory, session_scope
from core_engine.events import EventEnvelope
from core_engine.repository import mark_event_started, record_event_failure
from core_engine.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class ClickHouseEventBatcher:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = create_clickhouse_client(settings.clickhouse_dsn)
        self.rows: list[tuple] = []
        self.last_flush = time.monotonic()

    async def add(self, event: EventEnvelope) -> None:
        entity_id = str(event.data.get("id") or event.data.get("entity_id") or "")
        value_cents = int(event.data.get("value_cents") or 0)
        self.rows.append(
            (
                event.occurred_at,
                str(event.agency_id),
                event.event,
                entity_id,
                value_cents,
                json.dumps(event.data, ensure_ascii=True, default=str),
                str(event.trace_id),
                int(event.hops),
                str(event.event_id),
            )
        )
        if self.should_flush():
            await self.flush()

    def should_flush(self) -> bool:
        return (
            len(self.rows) >= self.settings.bi_batch_size
            or time.monotonic() - self.last_flush >= self.settings.bi_flush_seconds
        )

    async def flush(self) -> None:
        if not self.rows:
            return
        rows, self.rows = self.rows, []
        self.client.insert(
            "events_log",
            rows,
            column_names=[
                "occurred_at",
                "agency_id",
                "event_type",
                "entity_id",
                "value_cents",
                "meta",
                "trace_id",
                "hops",
                "event_id",
            ],
        )
        self.last_flush = time.monotonic()
        logger.info("flushed clickhouse batch", extra={"rows": len(rows)})


async def run(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    consumer_name = f"{socket.gethostname()}:bi"
    bus = RedisStreamBus.from_url(settings.redis_url)
    session_factory = create_session_factory(settings.database_url)
    batcher = ClickHouseEventBatcher(settings)

    await bus.ensure_group(settings.stream_bi, settings.worker_group)

    try:
        while True:
            messages = await bus.read_group(
                stream=settings.stream_bi,
                group=settings.worker_group,
                consumer=consumer_name,
                count=settings.bi_batch_size,
                block_ms=1000,
            )
            if not messages:
                if batcher.should_flush():
                    await batcher.flush()
                await asyncio.sleep(0)
                continue

            for message in messages:
                try:
                    async with session_scope(session_factory) as session:
                        is_new = await mark_event_started(
                            session, message.event, worker_role="bi"
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
                            await batcher.add(message.event)

                    await bus.ack(message.stream, settings.worker_group, message.message_id)
                except Exception:
                    logger.exception(
                        "bi event processing failed",
                        extra={"message_id": message.message_id},
                    )
    finally:
        await batcher.flush()
        await bus.close()
