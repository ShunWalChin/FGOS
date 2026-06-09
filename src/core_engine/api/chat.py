from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from core_engine.db import session_scope

router = APIRouter(prefix="/api", tags=["messaging"])


class ModeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str  # bot | human


def _factory(request: Request):
    return request.app.state.session_factory


@router.get("/contacts")
async def list_contacts(request: Request, agency_id: UUID, limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 500))
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                select id, full_name, email, phone, external_ids, tags, created_at
                from contacts where agency_id = :a
                order by created_at desc limit :l
                """
            ),
            {"a": str(agency_id), "l": limit},
        )
        rows = result.mappings().all()
    return [
        {
            "id": str(r["id"]),
            "full_name": r["full_name"],
            "email": r["email"],
            "phone": r["phone"],
            "external_ids": r["external_ids"],
            "tags": list(r["tags"] or []),
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


@router.get("/chat/sessions")
async def list_sessions(request: Request, agency_id: UUID, limit: int = 100) -> list[dict[str, Any]]:
    """Inbox: sessions with contact label, mode and last-message preview."""
    limit = max(1, min(limit, 200))
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                select s.id, s.channel, s.mode, s.updated_at,
                       coalesce(c.full_name, c.phone, c.email, 'Contato') as contact_label,
                       c.id as contact_id,
                       last.body as last_body, last.direction as last_direction
                from chat_sessions s
                join contacts c on c.id = s.contact_id
                left join lateral (
                    select body, direction from messages m
                    where m.session_id = s.id order by m.created_at desc limit 1
                ) last on true
                where s.agency_id = :a
                order by s.updated_at desc limit :l
                """
            ),
            {"a": str(agency_id), "l": limit},
        )
        rows = result.mappings().all()
    return [
        {
            "id": str(r["id"]),
            "channel": r["channel"],
            "mode": r["mode"],
            "contact_id": str(r["contact_id"]),
            "contact_label": r["contact_label"],
            "last_body": r["last_body"],
            "last_direction": r["last_direction"],
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


@router.get("/chat/sessions/{session_id}/messages")
async def list_messages(request: Request, session_id: UUID, limit: int = 200) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 500))
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                select id, direction, body, created_at
                from messages where session_id = :s
                order by created_at limit :l
                """
            ),
            {"s": str(session_id), "l": limit},
        )
        rows = result.mappings().all()
    return [
        {
            "id": str(r["id"]),
            "direction": r["direction"],
            "body": r["body"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


@router.patch("/chat/sessions/{session_id}/mode")
async def set_mode(session_id: UUID, payload: ModeIn, request: Request) -> dict[str, str]:
    if payload.mode not in ("bot", "human"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mode must be bot|human")
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text("update chat_sessions set mode = :m, updated_at = now() where id = :s returning id"),
            {"m": payload.mode, "s": str(session_id)},
        )
        if result.first() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return {"id": str(session_id), "mode": payload.mode}
