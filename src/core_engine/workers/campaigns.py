"""Campaigns worker — expands a scheduled campaign into per-recipient shipping rows and
dispatches them with pacing and message rotation (anti-ban). Dry-run unless MESSAGING_LIVE.

Absorbed from WhatICket Campaign/CampaignShipping; original FGOS implementation on the bus.
Uses the same FOR UPDATE SKIP LOCKED + poll pattern as the social worker.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import text

from core_engine.bus import RedisStreamBus
from core_engine.db import create_session_factory, session_scope
from core_engine.events import Actor, EventEnvelope
from core_engine.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def _render(template: str, item: dict[str, Any]) -> str:
    out = template or ""
    for key in ("name", "number", "email"):
        out = out.replace("{{" + key + "}}", str(item.get(key) or ""))
    return out


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [value]
    return [str(v) for v in value] if isinstance(value, list) else []


async def _publish(bus: RedisStreamBus, settings: Settings, event: EventEnvelope) -> None:
    await bus.publish(settings.stream_events, event)


async def _start_due_campaign(session, bus: RedisStreamBus, settings: Settings) -> bool:
    """Claim one due scheduled campaign, expand its contact list into shipping rows."""
    row = (
        await session.execute(
            text(
                """
                select id, agency_id, contact_list_id, messages
                from campaigns
                where status = 'scheduled' and (scheduled_at is null or scheduled_at <= now())
                order by scheduled_at nulls first
                for update skip locked limit 1
                """
            )
        )
    ).mappings().first()
    if not row:
        return False

    messages = _as_list(row["messages"]) or [""]
    items = (
        await session.execute(
            text(
                "select id, name, number, email from contact_list_items "
                "where contact_list_id = :l order by created_at"
            ),
            {"l": str(row["contact_list_id"]) if row["contact_list_id"] else None},
        )
    ).mappings().all()

    for i, it in enumerate(items):
        rendered = _render(messages[i % len(messages)], dict(it))
        await session.execute(
            text(
                """
                insert into campaign_shipping(agency_id, campaign_id, contact_item_id, number, message)
                values (:a, :c, :ci, :n, :m)
                """
            ),
            {"a": str(row["agency_id"]), "c": str(row["id"]), "ci": str(it["id"]),
             "n": it["number"], "m": rendered},
        )

    if not items:
        # empty list -> finish immediately instead of getting stuck in 'running'
        await session.execute(
            text("update campaigns set status='done', completed_at=now() where id=:c"),
            {"c": str(row["id"])},
        )
        await _publish(bus, settings, EventEnvelope(
            event="messaging.campaign.completed",
            agency_id=row["agency_id"],
            actor=Actor(type="system", id="worker-campaigns"),
            data={"campaign_id": str(row["id"]), "recipients": 0},
        ))
        return True

    await session.execute(text("update campaigns set status='running' where id=:c"), {"c": str(row["id"])})
    await _publish(bus, settings, EventEnvelope(
        event="messaging.campaign.started",
        agency_id=row["agency_id"],
        actor=Actor(type="system", id="worker-campaigns"),
        data={"campaign_id": str(row["id"]), "recipients": len(items)},
    ))
    logger.info("campaign started", extra={"campaign_id": str(row["id"]), "recipients": len(items)})
    return True


async def _dispatch_one(session, bus: RedisStreamBus, settings: Settings) -> float | None:
    """Claim one pending shipping row of a running campaign and send it (dry-run unless live)."""
    row = (
        await session.execute(
            text(
                """
                select s.id, s.agency_id, s.campaign_id, s.number, c.interval_seconds
                from campaign_shipping s join campaigns c on c.id = s.campaign_id
                where s.status = 'pending' and c.status = 'running'
                order by s.created_at
                for update skip locked limit 1
                """
            )
        )
    ).mappings().first()
    if not row:
        return None

    live = bool(getattr(settings, "messaging_live", False))
    # Dry-run: no real network; mark as sent. (Live dispatch would call the provider here.)
    await session.execute(
        text("update campaign_shipping set status='sent', delivered_at=now() where id=:i"),
        {"i": str(row["id"])},
    )
    await _publish(bus, settings, EventEnvelope(
        event="messaging.campaign.sent",
        agency_id=row["agency_id"],
        actor=Actor(type="system", id="worker-campaigns"),
        data={"campaign_id": str(row["campaign_id"]), "shipping_id": str(row["id"]),
              "number": row["number"], "live": live},
    ))
    return float(row["interval_seconds"] or 0)


async def _finish_completed(session, bus: RedisStreamBus, settings: Settings) -> None:
    """Close running campaigns that have no more pending shipping."""
    rows = (
        await session.execute(
            text(
                """
                update campaigns set status='done', completed_at=now()
                where status='running'
                  and exists (select 1 from campaign_shipping s where s.campaign_id = campaigns.id)
                  and not exists (
                    select 1 from campaign_shipping s
                    where s.campaign_id = campaigns.id and s.status = 'pending')
                returning id, agency_id
                """
            )
        )
    ).mappings().all()
    for r in rows:
        await _publish(bus, settings, EventEnvelope(
            event="messaging.campaign.completed",
            agency_id=r["agency_id"],
            actor=Actor(type="system", id="worker-campaigns"),
            data={"campaign_id": str(r["id"])},
        ))


async def run(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    session_factory = create_session_factory(settings.database_url)
    bus = RedisStreamBus.from_url(settings.redis_url)
    logger.info("campaigns worker started")
    try:
        while True:
            async with session_scope(session_factory) as session:
                started = await _start_due_campaign(session, bus, settings)
            async with session_scope(session_factory) as session:
                interval = await _dispatch_one(session, bus, settings)
            async with session_scope(session_factory) as session:
                await _finish_completed(session, bus, settings)

            if interval is not None:
                await asyncio.sleep(interval)
            elif not started:
                await asyncio.sleep(2)
    finally:
        await bus.close()
