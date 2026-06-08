from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from core_engine.events import EventEnvelope


@dataclass(frozen=True)
class StreamMessage:
    stream: str
    message_id: str
    event: EventEnvelope


class RedisStreamBus:
    """Small wrapper around Redis Streams for canonical event envelopes."""

    def __init__(self, redis: Redis):
        self.redis = redis

    @classmethod
    def from_url(cls, url: str) -> "RedisStreamBus":
        return cls(Redis.from_url(url, decode_responses=False))

    async def close(self) -> None:
        await self.redis.aclose()

    async def publish(self, stream: str, event: EventEnvelope) -> str:
        message_id = await self.redis.xadd(stream, {"payload": event.to_stream_payload()})
        return _decode(message_id)

    async def ensure_group(self, stream: str, group: str) -> None:
        try:
            await self.redis.xgroup_create(stream, group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def read_group(
        self,
        *,
        stream: str,
        group: str,
        consumer: str,
        count: int = 10,
        block_ms: int = 5000,
    ) -> list[StreamMessage]:
        response = await self.redis.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={stream: ">"},
            count=count,
            block=block_ms,
        )

        messages: list[StreamMessage] = []
        for raw_stream, raw_items in response:
            stream_name = _decode(raw_stream)
            for raw_id, fields in raw_items:
                payload = _decode(fields[b"payload"])
                messages.append(
                    StreamMessage(
                        stream=stream_name,
                        message_id=_decode(raw_id),
                        event=EventEnvelope.from_stream_payload(payload),
                    )
                )
        return messages

    async def ack(self, stream: str, group: str, message_id: str) -> None:
        await self.redis.xack(stream, group, message_id)

    async def add_to_debounce(self, key: str, value: str, ttl_seconds: int) -> None:
        await self.redis.rpush(key, value)
        await self.redis.expire(key, ttl_seconds)

    async def drain_list(self, key: str) -> list[str]:
        values = await self.redis.lrange(key, 0, -1)
        await self.redis.delete(key)
        return [_decode(value) for value in values]


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
