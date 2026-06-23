"""Campaigns API — contact lists + bulk campaigns (Module C extension).

Original FGOS implementation of patterns absorbed from WhatICket/WASender. Campaign dispatch is
handled by the campaigns worker (dry-run unless MESSAGING_LIVE). See docs/REVERSE-ENGINEERING-KB.md.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from core_engine.api.deps import Principal, get_principal
from core_engine.db import session_scope

router = APIRouter(prefix="/api", tags=["campaigns"])


# --------------------------------------------------------------------------- schemas
class ContactListIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)


class ContactItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = ""
    number: str = Field(min_length=1, max_length=64)
    email: str | None = None


class ContactItemsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ContactItemIn] = Field(min_length=1)


class CampaignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    contact_list_id: UUID
    messages: list[str] = Field(min_length=1)   # rotation pool (anti-ban)
    interval_seconds: int = 5
    schedule_now: bool = False


class CampaignAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str  # schedule | cancel


def _factory(request: Request):
    return request.app.state.session_factory


async def _owns_list(session, list_id: UUID, agency_id) -> bool:
    r = await session.execute(
        text("select 1 from contact_lists where id = :l and agency_id = :a"),
        {"l": str(list_id), "a": str(agency_id)},
    )
    return r.first() is not None


# --------------------------------------------------------------------------- contact lists
@router.get("/contact-lists")
async def list_contact_lists(
    request: Request, principal: Principal = Depends(get_principal)
) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text(
                    """
                    select cl.id, cl.name, cl.created_at,
                           (select count(*) from contact_list_items i where i.contact_list_id = cl.id) as items
                    from contact_lists cl where cl.agency_id = :a order by cl.created_at desc
                    """
                ),
                {"a": str(principal.agency_id)},
            )
        ).mappings().all()
    return [
        {"id": str(r["id"]), "name": r["name"], "items": r["items"],
         "created_at": r["created_at"].isoformat()}
        for r in rows
    ]


@router.post("/contact-lists", status_code=status.HTTP_201_CREATED)
async def create_contact_list(
    payload: ContactListIn, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text("insert into contact_lists(agency_id, name) values (:a, :n) returning id"),
            {"a": str(principal.agency_id), "n": payload.name},
        )
        return {"id": str(result.scalar_one())}


@router.post("/contact-lists/{list_id}/items", status_code=status.HTTP_201_CREATED)
async def add_items(
    list_id: UUID, payload: ContactItemsIn, request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, int]:
    async with session_scope(_factory(request)) as session:
        if not await _owns_list(session, list_id, principal.agency_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="list not found")
        for it in payload.items:
            await session.execute(
                text(
                    """
                    insert into contact_list_items(agency_id, contact_list_id, name, number, email)
                    values (:a, :l, :n, :num, :e)
                    """
                ),
                {"a": str(principal.agency_id), "l": str(list_id), "n": it.name,
                 "num": it.number, "e": it.email},
            )
    return {"added": len(payload.items)}


# --------------------------------------------------------------------------- campaigns
@router.get("/campaigns")
async def list_campaigns(
    request: Request, principal: Principal = Depends(get_principal)
) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text(
                    """
                    select c.id, c.name, c.status, c.interval_seconds, c.scheduled_at, c.completed_at,
                           c.created_at, cl.name as list_name,
                           (select count(*) from campaign_shipping s where s.campaign_id = c.id) as total,
                           (select count(*) from campaign_shipping s where s.campaign_id = c.id and s.status='sent') as sent
                    from campaigns c left join contact_lists cl on cl.id = c.contact_list_id
                    where c.agency_id = :a order by c.created_at desc
                    """
                ),
                {"a": str(principal.agency_id)},
            )
        ).mappings().all()
    return [
        {"id": str(r["id"]), "name": r["name"], "status": r["status"],
         "interval_seconds": r["interval_seconds"], "list_name": r["list_name"],
         "total": r["total"], "sent": r["sent"],
         "scheduled_at": r["scheduled_at"].isoformat() if r["scheduled_at"] else None,
         "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
         "created_at": r["created_at"].isoformat()}
        for r in rows
    ]


@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignIn, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        if not await _owns_list(session, payload.contact_list_id, principal.agency_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="contact_list not found")
        new_status = "scheduled" if payload.schedule_now else "draft"
        result = await session.execute(
            text(
                """
                insert into campaigns(agency_id, name, contact_list_id, messages, status,
                                      scheduled_at, interval_seconds)
                values (:a, :n, :l, cast(:m as jsonb), :st,
                        case when :sch then now() else null end, :iv)
                returning id
                """
            ),
            {"a": str(principal.agency_id), "n": payload.name, "l": str(payload.contact_list_id),
             "m": json.dumps(payload.messages), "st": new_status,
             "sch": payload.schedule_now, "iv": max(0, payload.interval_seconds)},
        )
        return {"id": str(result.scalar_one())}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: UUID, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, Any]:
    async with session_scope(_factory(request)) as session:
        row = (
            await session.execute(
                text(
                    """
                    select c.*, cl.name as list_name,
                           (select count(*) from campaign_shipping s where s.campaign_id = c.id) as total,
                           (select count(*) from campaign_shipping s where s.campaign_id = c.id and s.status='sent') as sent
                    from campaigns c left join contact_lists cl on cl.id = c.contact_list_id
                    where c.id = :id and c.agency_id = :a
                    """
                ),
                {"id": str(campaign_id), "a": str(principal.agency_id)},
            )
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    out = {k: (str(v) if hasattr(v, "hex") else v) for k, v in dict(row).items()}
    for key in ("scheduled_at", "completed_at", "created_at"):
        if row.get(key) is not None and hasattr(row[key], "isoformat"):
            out[key] = row[key].isoformat()
    if isinstance(out.get("messages"), str):
        try:
            out["messages"] = json.loads(out["messages"])
        except json.JSONDecodeError:
            pass
    return out


@router.patch("/campaigns/{campaign_id}")
async def act_on_campaign(
    campaign_id: UUID, payload: CampaignAction, request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, str]:
    if payload.action not in ("schedule", "cancel"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="action must be schedule|cancel")
    if payload.action == "schedule":
        sql = ("update campaigns set status='scheduled', scheduled_at=now() "
               "where id=:id and agency_id=:a and status in ('draft','scheduled') returning status")
    else:
        sql = ("update campaigns set status='cancelled' "
               "where id=:id and agency_id=:a and status in ('draft','scheduled','running') returning status")
    async with session_scope(_factory(request)) as session:
        row = (await session.execute(text(sql), {"id": str(campaign_id), "a": str(principal.agency_id)})).first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="campaign not in a valid state")
    return {"id": str(campaign_id), "status": row[0]}
