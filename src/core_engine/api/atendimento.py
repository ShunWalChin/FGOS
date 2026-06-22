"""Atendimento — multi-agent inbox / ticketing API (Module C extension).

Original FGOS implementation of patterns absorbed from WhatICket (see
docs/REVERSE-ENGINEERING-KB.md): Ticket lifecycle, Queue routing and bot delegation.
Every state transition emits a canonical event on stream:events (so it mirrors to BI)
and is recorded in ticket_traking for audit.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from core_engine.api.deps import Principal, get_principal
from core_engine.bus import RedisStreamBus
from core_engine.db import session_scope
from core_engine.events import Actor, EventEnvelope
from core_engine.settings import Settings

router = APIRouter(prefix="/api", tags=["atendimento"])

VALID_STATUS = {"pending", "open", "closed"}


# --------------------------------------------------------------------------- schemas
class QueueIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    color: str = "#00f0ff"
    greeting_message: str = ""
    out_of_hours_message: str = ""


class TicketIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_id: UUID
    session_id: UUID | None = None
    queue_id: UUID | None = None
    channel: str = "whatsapp"
    last_message: str | None = None


class TicketPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str | None = None
    queue_id: UUID | None = None
    assigned_user_id: UUID | None = None
    rating: int | None = None


class QueueOptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    message: str = ""
    option: str = Field(min_length=1, max_length=40)   # key/keyword the user types
    parent_id: UUID | None = None


class QueueIntegrationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str  # n8n | typebot | openai | dialogflow
    name: str = Field(min_length=1, max_length=200)
    queue_id: UUID | None = None
    url_n8n: str | None = None
    prompt: str | None = None


class TemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    shortcut: str | None = None


class TemplateRender(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variables: dict[str, str] = Field(default_factory=dict)


# --------------------------------------------------------------------------- helpers
def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _bus(request: Request) -> RedisStreamBus:
    return request.app.state.bus


def _factory(request: Request):
    return request.app.state.session_factory


async def _publish(bus: RedisStreamBus, settings: Settings, event: EventEnvelope) -> None:
    await bus.publish(settings.stream_events, event)


async def _track(session, agency_id, ticket_id, action: str, user_id=None, detail: str | None = None) -> None:
    await session.execute(
        text(
            """
            insert into ticket_traking(agency_id, ticket_id, user_id, action, detail)
            values (:a, :t, :u, :act, :d)
            """
        ),
        {"a": str(agency_id), "t": str(ticket_id), "u": str(user_id) if user_id else None,
         "act": action, "d": detail},
    )


# --------------------------------------------------------------------------- queues
@router.get("/queues")
async def list_queues(
    request: Request, principal: Principal = Depends(get_principal)
) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                select id, name, color, greeting_message, out_of_hours_message, created_at
                from queues where agency_id = :a order by created_at
                """
            ),
            {"a": str(principal.agency_id)},
        )
        rows = result.mappings().all()
    return [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "color": r["color"],
            "greeting_message": r["greeting_message"],
            "out_of_hours_message": r["out_of_hours_message"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


@router.post("/queues", status_code=status.HTTP_201_CREATED)
async def create_queue(
    payload: QueueIn, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                insert into queues(agency_id, name, color, greeting_message, out_of_hours_message)
                values (:a, :n, :c, :g, :o) returning id
                """
            ),
            {"a": str(principal.agency_id), "n": payload.name, "c": payload.color,
             "g": payload.greeting_message, "o": payload.out_of_hours_message},
        )
        queue_id = str(result.scalar_one())
    return {"id": queue_id}


# --------------------------------------------------------------------------- tickets
@router.get("/tickets")
async def list_tickets(
    request: Request,
    principal: Principal = Depends(get_principal),
    status_filter: str | None = None,
    queue_id: UUID | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 200))
    clauses = ["t.agency_id = :a"]
    params: dict[str, Any] = {"a": str(principal.agency_id), "l": limit}
    if status_filter in VALID_STATUS:
        clauses.append("t.status = :st")
        params["st"] = status_filter
    if queue_id:
        clauses.append("t.queue_id = :q")
        params["q"] = str(queue_id)
    where = " and ".join(clauses)
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                f"""
                select t.id, t.status, t.channel, t.unread_count, t.last_message,
                       t.queue_id, t.assigned_user_id, t.updated_at,
                       coalesce(c.full_name, c.phone, c.email, 'Contato') as contact_label,
                       c.id as contact_id, q.name as queue_name, u.full_name as agent_name
                from tickets t
                join contacts c on c.id = t.contact_id
                left join queues q on q.id = t.queue_id
                left join app_users u on u.id = t.assigned_user_id
                where {where}
                order by t.updated_at desc limit :l
                """
            ),
            params,
        )
        rows = result.mappings().all()
    return [
        {
            "id": str(r["id"]),
            "status": r["status"],
            "channel": r["channel"],
            "unread_count": r["unread_count"],
            "last_message": r["last_message"],
            "contact_id": str(r["contact_id"]),
            "contact_label": r["contact_label"],
            "queue_id": str(r["queue_id"]) if r["queue_id"] else None,
            "queue_name": r["queue_name"],
            "assigned_user_id": str(r["assigned_user_id"]) if r["assigned_user_id"] else None,
            "agent_name": r["agent_name"],
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


@router.post("/tickets", status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketIn, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        # D1: validate referenced rows belong to the caller's agency (no cross-tenant writes)
        owns_contact = await session.execute(
            text("select 1 from contacts where id = :c and agency_id = :a"),
            {"c": str(payload.contact_id), "a": str(principal.agency_id)},
        )
        if owns_contact.first() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="contact not found")
        if payload.queue_id is not None:
            owns_queue = await session.execute(
                text("select 1 from queues where id = :q and agency_id = :a"),
                {"q": str(payload.queue_id), "a": str(principal.agency_id)},
            )
            if owns_queue.first() is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="queue not found")
        result = await session.execute(
            text(
                """
                insert into tickets(agency_id, contact_id, session_id, queue_id, channel, last_message)
                values (:a, :c, :s, :q, :ch, :lm) returning id
                """
            ),
            {"a": str(principal.agency_id), "c": str(payload.contact_id),
             "s": str(payload.session_id) if payload.session_id else None,
             "q": str(payload.queue_id) if payload.queue_id else None,
             "ch": payload.channel, "lm": payload.last_message},
        )
        ticket_id = str(result.scalar_one())
        await _track(session, principal.agency_id, ticket_id, "created", detail=payload.channel)

    event = EventEnvelope(
        event="messaging.ticket.created",
        agency_id=principal.agency_id,
        actor=Actor(type="user", id="api"),
        data={"ticket_id": ticket_id, "contact_id": str(payload.contact_id),
              "queue_id": str(payload.queue_id) if payload.queue_id else None,
              "channel": payload.channel, "status": "pending"},
    )
    await _publish(_bus(request), _settings(request), event)
    if payload.queue_id is not None:
        await _maybe_dispatch_integration(
            request, principal, ticket_id, payload.queue_id, payload.last_message
        )
    return {"id": ticket_id}


@router.get("/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: UUID, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, Any]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                select t.*, coalesce(c.full_name, c.phone, c.email, 'Contato') as contact_label
                from tickets t join contacts c on c.id = t.contact_id
                where t.id = :id and t.agency_id = :a
                """
            ),
            {"id": str(ticket_id), "a": str(principal.agency_id)},
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        trk = await session.execute(
            text("select action, detail, created_at from ticket_traking where ticket_id = :t order by created_at"),
            {"t": str(ticket_id)},
        )
        history = trk.mappings().all()
    out = {k: (str(v) if hasattr(v, "hex") else v) for k, v in dict(row).items()}
    for key in ("created_at", "updated_at"):
        if out.get(key) is not None and hasattr(row[key], "isoformat"):
            out[key] = row[key].isoformat()
    out["history"] = [
        {"action": h["action"], "detail": h["detail"], "at": h["created_at"].isoformat()}
        for h in history
    ]
    return out


@router.patch("/tickets/{ticket_id}")
async def update_ticket(
    ticket_id: UUID, payload: TicketPatch, request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    if payload.status is not None and payload.status not in VALID_STATUS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="status must be pending|open|closed")

    sets: list[str] = ["updated_at = now()"]
    params: dict[str, Any] = {"id": str(ticket_id), "a": str(principal.agency_id)}
    actions: list[tuple[str, str | None]] = []

    if payload.status is not None:
        sets.append("status = :st")
        params["st"] = payload.status
        actions.append(("opened" if payload.status == "open" else
                        "closed" if payload.status == "closed" else "queued", payload.status))
    if payload.queue_id is not None:
        sets.append("queue_id = :q")
        params["q"] = str(payload.queue_id)
        actions.append(("queued", str(payload.queue_id)))
    if payload.assigned_user_id is not None:
        sets.append("assigned_user_id = :u")
        params["u"] = str(payload.assigned_user_id)
        actions.append(("assigned", str(payload.assigned_user_id)))
    if payload.rating is not None:
        sets.append("rating = :r")
        params["r"] = payload.rating
        actions.append(("rated", str(payload.rating)))

    if not actions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="nothing to update")

    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(f"update tickets set {', '.join(sets)} where id = :id and agency_id = :a returning status, queue_id, assigned_user_id"),
            params,
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        for action, detail in actions:
            await _track(session, principal.agency_id, ticket_id, action,
                         user_id=payload.assigned_user_id if action == "assigned" else None, detail=detail)

    for action, detail in actions:
        event = EventEnvelope(
            event="messaging.ticket.updated",
            agency_id=principal.agency_id,
            actor=Actor(type="user", id="api"),
            data={"ticket_id": str(ticket_id), "action": action, "detail": detail,
                  "status": row["status"]},
        )
        await _publish(_bus(request), _settings(request), event)

    return {"id": str(ticket_id), "status": row["status"],
            "queue_id": str(row["queue_id"]) if row["queue_id"] else None,
            "assigned_user_id": str(row["assigned_user_id"]) if row["assigned_user_id"] else None}


# --------------------------------------------------------------------------- chatbot tree (queue_options)
@router.get("/queues/{queue_id}/options")
async def list_queue_options(
    queue_id: UUID, request: Request, principal: Principal = Depends(get_principal)
) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text(
                    "select id, parent_id, title, message, option from queue_options "
                    "where queue_id = :q and agency_id = :a order by created_at"
                ),
                {"q": str(queue_id), "a": str(principal.agency_id)},
            )
        ).mappings().all()
    return [
        {"id": str(r["id"]), "parent_id": str(r["parent_id"]) if r["parent_id"] else None,
         "title": r["title"], "message": r["message"], "option": r["option"]}
        for r in rows
    ]


@router.post("/queues/{queue_id}/options", status_code=status.HTTP_201_CREATED)
async def create_queue_option(
    queue_id: UUID, payload: QueueOptionIn, request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        owns = await session.execute(
            text("select 1 from queues where id = :q and agency_id = :a"),
            {"q": str(queue_id), "a": str(principal.agency_id)},
        )
        if owns.first() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="queue not found")
        result = await session.execute(
            text(
                "insert into queue_options(agency_id, queue_id, parent_id, title, message, option) "
                "values (:a, :q, :p, :t, :m, :o) returning id"
            ),
            {"a": str(principal.agency_id), "q": str(queue_id),
             "p": str(payload.parent_id) if payload.parent_id else None,
             "t": payload.title, "m": payload.message, "o": payload.option},
        )
        return {"id": str(result.scalar_one())}


# --------------------------------------------------------------------------- queue integrations (n8n/openai)
@router.get("/queue-integrations")
async def list_queue_integrations(
    request: Request, principal: Principal = Depends(get_principal)
) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text(
                    "select id, queue_id, type, name, url_n8n, active from queue_integrations "
                    "where agency_id = :a order by created_at"
                ),
                {"a": str(principal.agency_id)},
            )
        ).mappings().all()
    return [
        {"id": str(r["id"]), "queue_id": str(r["queue_id"]) if r["queue_id"] else None,
         "type": r["type"], "name": r["name"], "url_n8n": r["url_n8n"], "active": r["active"]}
        for r in rows
    ]


@router.post("/queue-integrations", status_code=status.HTTP_201_CREATED)
async def create_queue_integration(
    payload: QueueIntegrationIn, request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, str]:
    if payload.type not in ("n8n", "typebot", "openai", "dialogflow"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid integration type")
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                "insert into queue_integrations(agency_id, queue_id, type, name, url_n8n, prompt) "
                "values (:a, :q, :ty, :n, :u, :pr) returning id"
            ),
            {"a": str(principal.agency_id),
             "q": str(payload.queue_id) if payload.queue_id else None,
             "ty": payload.type, "n": payload.name, "u": payload.url_n8n, "pr": payload.prompt},
        )
        return {"id": str(result.scalar_one())}


async def _maybe_dispatch_integration(request, principal, ticket_id, queue_id, last_message) -> None:
    """If the ticket's queue has an active integration, route the conversation to it.
    Dry-run by default (emits messaging.integration.dispatched). Live n8n: POSTs to url_n8n.
    This is the bridge that lets FGOS's own n8n drive the bot for a department/queue.
    """
    settings = _settings(request)
    async with session_scope(_factory(request)) as session:
        integ = (
            await session.execute(
                text(
                    "select id, type, url_n8n from queue_integrations "
                    "where queue_id = :q and agency_id = :a and active = true "
                    "order by created_at limit 1"
                ),
                {"q": str(queue_id), "a": str(principal.agency_id)},
            )
        ).mappings().first()
    if not integ:
        return

    live = bool(getattr(settings, "messaging_live", False))
    delivered = False
    if live and integ["type"] == "n8n" and integ["url_n8n"]:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                await client.post(
                    integ["url_n8n"],
                    json={"ticket_id": str(ticket_id), "agency_id": str(principal.agency_id),
                          "message": last_message},
                )
            delivered = True
        except Exception:
            delivered = False

    await _publish(_bus(request), settings, EventEnvelope(
        event="messaging.integration.dispatched",
        agency_id=principal.agency_id,
        actor=Actor(type="system", id="api"),
        data={"ticket_id": str(ticket_id), "integration_id": str(integ["id"]),
              "type": integ["type"], "live": live, "delivered": delivered},
    ))


# --------------------------------------------------------------------------- templates / quick replies
@router.get("/templates")
async def list_templates(
    request: Request, principal: Principal = Depends(get_principal)
) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text("select id, name, body, shortcut from message_templates "
                     "where agency_id = :a order by name"),
                {"a": str(principal.agency_id)},
            )
        ).mappings().all()
    return [
        {"id": str(r["id"]), "name": r["name"], "body": r["body"], "shortcut": r["shortcut"]}
        for r in rows
    ]


@router.post("/templates", status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateIn, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text("insert into message_templates(agency_id, name, body, shortcut) "
                 "values (:a, :n, :b, :s) returning id"),
            {"a": str(principal.agency_id), "n": payload.name, "b": payload.body, "s": payload.shortcut},
        )
        return {"id": str(result.scalar_one())}


@router.post("/templates/{template_id}/render")
async def render_template(
    template_id: UUID, payload: TemplateRender, request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        row = (
            await session.execute(
                text("select body from message_templates where id = :id and agency_id = :a"),
                {"id": str(template_id), "a": str(principal.agency_id)},
            )
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    rendered = row["body"]
    for key, value in payload.variables.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return {"rendered": rendered}
