from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core_engine.events import EventEnvelope


async def mark_event_started(
    session: AsyncSession,
    event: EventEnvelope,
    *,
    worker_role: str = "default",
) -> bool:
    """Return False when this event was already processed by the given worker role."""

    result = await session.execute(
        text(
            """
            insert into processed_events(event_id, event_type, worker_role)
            values (:event_id, :event_type, :worker_role)
            on conflict (event_id, worker_role) do nothing
            """
        ),
        {
            "event_id": str(event.event_id),
            "event_type": event.event,
            "worker_role": worker_role,
        },
    )
    return result.rowcount == 1


async def record_event_failure(
    session: AsyncSession,
    event: EventEnvelope,
    *,
    reason: str,
    detail: str | None = None,
) -> None:
    await session.execute(
        text(
            """
            insert into event_failures(event_id, event_type, trace_id, reason, detail)
            values (:event_id, :event_type, :trace_id, :reason, :detail)
            """
        ),
        {
            "event_id": str(event.event_id),
            "event_type": event.event,
            "trace_id": str(event.trace_id),
            "reason": reason,
            "detail": detail,
        },
    )


async def claim_next_social_post(
    session: AsyncSession,
    *,
    worker_id: str,
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            """
            update posts_queue
            set status = 'processing',
                locked_at = now(),
                locked_by = :worker_id,
                attempts = attempts + 1
            where id = (
              select id from posts_queue
              where status = 'pending'
                and scheduled_at <= now()
                and (next_attempt_at is null or next_attempt_at <= now())
              order by scheduled_at
              for update skip locked
              limit 1
            )
            returning *
            """
        ),
        {"worker_id": worker_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def mark_social_post_published(
    session: AsyncSession,
    *,
    post_id: str,
) -> None:
    await session.execute(
        text(
            """
            update posts_queue
            set status = 'published',
                published_at = now(),
                locked_at = null,
                locked_by = null,
                last_error = null
            where id = :post_id
            """
        ),
        {"post_id": post_id},
    )


async def mark_social_post_failed(
    session: AsyncSession,
    *,
    post_id: str,
    error: str,
    max_attempts: int = 5,
) -> None:
    await session.execute(
        text(
            """
            update posts_queue
            set status = case when attempts >= :max_attempts then 'failed' else 'pending' end,
                next_attempt_at = now() + (interval '1 minute' * power(3, attempts)),
                last_error = :error,
                locked_at = null,
                locked_by = null
            where id = :post_id
            """
        ),
        {"post_id": post_id, "error": error, "max_attempts": max_attempts},
    )
