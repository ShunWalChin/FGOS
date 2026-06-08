from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core_engine.events import Actor, EventEnvelope
from core_engine.settings import Settings, get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from core_engine.bus import RedisStreamBus

logger = logging.getLogger(__name__)

WORKER_ROLE = "router"


async def handle(
    event: EventEnvelope,
    session: "AsyncSession",
    bus: "RedisStreamBus",
    settings: Settings,
) -> None:
    if event.event == "workspace.item.created" and event.data.get("convert_to_deal"):
        await _create_deal_from_item(event, session, bus, settings)

    await bus.publish(settings.stream_bi, event)


async def _create_deal_from_item(
    event: EventEnvelope,
    session: "AsyncSession",
    bus: "RedisStreamBus",
    settings: Settings,
) -> None:
    from sqlalchemy import text

    data = event.data
    pipeline_id = data.get("pipeline_id")
    stage_id = data.get("stage_id")

    if not pipeline_id or not stage_id:
        resolved = await _resolve_default_pipeline_stage(session, event.agency_id)
        if not resolved:
            logger.warning(
                "skip deal creation — no pipeline/stage configured",
                extra={"agency_id": str(event.agency_id), "item_id": data.get("item_id")},
            )
            return
        pipeline_id, stage_id = resolved

    title = data.get("title") or f"Item {data.get('item_id')}"
    value_cents = int(data.get("value_cents") or 0)

    result = await session.execute(
        text(
            """
            insert into deals(agency_id, pipeline_id, stage_id, title, value_cents)
            values (:agency_id, :pipeline_id, :stage_id, :title, :value_cents)
            returning id
            """
        ),
        {
            "agency_id": str(event.agency_id),
            "pipeline_id": str(pipeline_id),
            "stage_id": str(stage_id),
            "title": title,
            "value_cents": value_cents,
        },
    )
    deal_id = str(result.scalar_one())

    child = event.child(
        event="crm.deal.created",
        data={
            "deal_id": deal_id,
            "pipeline_id": str(pipeline_id),
            "stage_id": str(stage_id),
            "value_cents": value_cents,
            "source": "workspace.item",
            "source_item_id": data.get("item_id"),
        },
        actor=Actor(type="system", id="worker-router"),
    )
    await bus.publish(settings.stream_events, child)


async def _resolve_default_pipeline_stage(
    session: "AsyncSession",
    agency_id,
) -> tuple[str, str] | None:
    from sqlalchemy import text

    result = await session.execute(
        text(
            """
            select p.id as pipeline_id, s.id as stage_id
            from pipelines p
            join stages s on s.pipeline_id = p.id
            where p.agency_id = :agency_id
            order by s.sort_order
            limit 1
            """
        ),
        {"agency_id": str(agency_id)},
    )
    row = result.mappings().first()
    if not row:
        return None
    return str(row["pipeline_id"]), str(row["stage_id"])


async def run(settings: Settings | None = None) -> None:
    from core_engine.workers.runtime import run_stream_worker

    settings = settings or get_settings()
    await run_stream_worker(
        stream=settings.stream_events,
        handler=handle,
        settings=settings,
        worker_role=WORKER_ROLE,
    )
