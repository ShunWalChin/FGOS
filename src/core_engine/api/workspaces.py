from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from core_engine.api.deps import Principal, get_principal
from core_engine.bus import RedisStreamBus
from core_engine.db import session_scope
from core_engine.events import Actor, EventEnvelope
from core_engine.settings import Settings

router = APIRouter(prefix="/api", tags=["workspace"])


class WorkspaceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)


class ListIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: UUID
    name: str = Field(min_length=1, max_length=200)
    parent_id: UUID | None = None
    sort_order: float = 0.0


class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    list_id: UUID
    title: str = Field(min_length=1, max_length=500)
    status: str = "open"
    fields: dict[str, Any] = Field(default_factory=dict)
    convert_to_deal: bool = False
    pipeline_id: UUID | None = None
    stage_id: UUID | None = None
    value_cents: int = 0


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _bus(request: Request) -> RedisStreamBus:
    return request.app.state.bus


def _factory(request: Request):
    return request.app.state.session_factory


async def _publish(bus: RedisStreamBus, settings: Settings, event: EventEnvelope) -> None:
    await bus.publish(settings.stream_events, event)


@router.get("/workspaces")
async def list_workspaces(
    request: Request,
    principal: Principal = Depends(get_principal),
) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text("select id, name, created_at from workspaces where agency_id = :a order by created_at"),
            {"a": str(principal.agency_id)},
        )
        rows = result.mappings().all()
    return [
        {"id": str(r["id"]), "name": r["name"], "created_at": r["created_at"].isoformat()}
        for r in rows
    ]


@router.get("/lists")
async def list_lists(request: Request, workspace_id: UUID) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                select l.id, l.name, l.sort_order,
                       (select count(*) from items i where i.list_id = l.id) as item_count
                from lists l where l.workspace_id = :w order by l.sort_order
                """
            ),
            {"w": str(workspace_id)},
        )
        rows = result.mappings().all()
    return [
        {"id": str(r["id"]), "name": r["name"], "sort_order": r["sort_order"], "item_count": r["item_count"]}
        for r in rows
    ]


@router.get("/items")
async def list_items(request: Request, list_id: UUID) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                select id, title, status, fields, due_at, sort_order, updated_at
                from items where list_id = :l order by sort_order, created_at
                """
            ),
            {"l": str(list_id)},
        )
        rows = result.mappings().all()
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "status": r["status"],
            "fields": r["fields"],
            "due_at": r["due_at"].isoformat() if r["due_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


@router.post("/workspaces", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceIn,
    request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                insert into workspaces(agency_id, name)
                values (:agency_id, :name)
                returning id
                """
            ),
            {"agency_id": str(principal.agency_id), "name": payload.name},
        )
        workspace_id = str(result.scalar_one())

    event = EventEnvelope(
        event="workspace.created",
        agency_id=principal.agency_id,
        actor=Actor(type="user", id="api"),
        data={"workspace_id": workspace_id, "name": payload.name},
    )
    await _publish(_bus(request), _settings(request), event)
    return {"id": workspace_id}


@router.post("/lists", status_code=status.HTTP_201_CREATED)
async def create_list(payload: ListIn, request: Request) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                insert into lists(workspace_id, parent_id, name, sort_order)
                values (:workspace_id, :parent_id, :name, :sort_order)
                returning id
                """
            ),
            {
                "workspace_id": str(payload.workspace_id),
                "parent_id": str(payload.parent_id) if payload.parent_id else None,
                "name": payload.name,
                "sort_order": payload.sort_order,
            },
        )
        list_id = str(result.scalar_one())
    return {"id": list_id}


@router.post("/items", status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: ItemIn,
    request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                insert into items(list_id, agency_id, title, status, fields)
                values (:list_id, :agency_id, :title, :status, cast(:fields as jsonb))
                returning id
                """
            ),
            {
                "list_id": str(payload.list_id),
                "agency_id": str(principal.agency_id),
                "title": payload.title,
                "status": payload.status,
                "fields": json.dumps(payload.fields, ensure_ascii=True, default=str),
            },
        )
        item_id = str(result.scalar_one())

    event = EventEnvelope(
        event="workspace.item.created",
        agency_id=principal.agency_id,
        actor=Actor(type="user", id="api"),
        data={
            "item_id": item_id,
            "list_id": str(payload.list_id),
            "title": payload.title,
            "convert_to_deal": payload.convert_to_deal,
            "pipeline_id": str(payload.pipeline_id) if payload.pipeline_id else None,
            "stage_id": str(payload.stage_id) if payload.stage_id else None,
            "value_cents": payload.value_cents,
        },
    )
    await _publish(_bus(request), _settings(request), event)
    return {"id": item_id}


@router.get("/items/{item_id}")
async def get_item(item_id: UUID, request: Request) -> dict[str, Any]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text("select id, list_id, agency_id, title, status, fields from items where id = :id"),
            {"id": str(item_id)},
        )
        row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return {k: (str(v) if hasattr(v, "hex") else v) for k, v in dict(row).items()}
