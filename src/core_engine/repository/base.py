from __future__ import annotations

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
