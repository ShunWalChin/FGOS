from __future__ import annotations

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

router = APIRouter(prefix="/api", tags=["crm"])


class PipelineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)


class StageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pipeline_id: UUID
    name: str = Field(min_length=1, max_length=200)
    sort_order: float = 0.0
    is_won: bool = False
    is_lost: bool = False


class DealIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pipeline_id: UUID
    stage_id: UUID
    title: str = Field(min_length=1, max_length=500)
    value_cents: int = 0
    currency: str = "BRL"
    contact_id: UUID | None = None
    sort_order: float = 0.0


class DealMove(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage_id: UUID
    sort_order: float
    version: int


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _bus(request: Request) -> RedisStreamBus:
    return request.app.state.bus


def _factory(request: Request):
    return request.app.state.session_factory


async def _publish(bus: RedisStreamBus, settings: Settings, event: EventEnvelope) -> None:
    await bus.publish(settings.stream_events, event)


@router.get("/pipelines")
async def list_pipelines(
    request: Request,
    principal: Principal = Depends(get_principal),
) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text("select id, name from pipelines where agency_id = :a order by name"),
            {"a": str(principal.agency_id)},
        )
        rows = result.mappings().all()
    return [{"id": str(r["id"]), "name": r["name"]} for r in rows]


@router.get("/stages")
async def list_stages(request: Request, pipeline_id: UUID) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                select id, name, sort_order, is_won, is_lost
                from stages where pipeline_id = :p order by sort_order
                """
            ),
            {"p": str(pipeline_id)},
        )
        rows = result.mappings().all()
    return [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "sort_order": r["sort_order"],
            "is_won": r["is_won"],
            "is_lost": r["is_lost"],
        }
        for r in rows
    ]


@router.post("/pipelines", status_code=status.HTTP_201_CREATED)
async def create_pipeline(
    payload: PipelineIn,
    request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                insert into pipelines(agency_id, name)
                values (:agency_id, :name)
                returning id
                """
            ),
            {"agency_id": str(principal.agency_id), "name": payload.name},
        )
        pipeline_id = str(result.scalar_one())
    return {"id": pipeline_id}


@router.post("/stages", status_code=status.HTTP_201_CREATED)
async def create_stage(payload: StageIn, request: Request) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                insert into stages(pipeline_id, name, sort_order, is_won, is_lost)
                values (:pipeline_id, :name, :sort_order, :is_won, :is_lost)
                returning id
                """
            ),
            {
                "pipeline_id": str(payload.pipeline_id),
                "name": payload.name,
                "sort_order": payload.sort_order,
                "is_won": payload.is_won,
                "is_lost": payload.is_lost,
            },
        )
        stage_id = str(result.scalar_one())
    return {"id": stage_id}


@router.post("/deals", status_code=status.HTTP_201_CREATED)
async def create_deal(
    payload: DealIn,
    request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                insert into deals(agency_id, pipeline_id, stage_id, contact_id, title,
                                  value_cents, currency, sort_order)
                values (:agency_id, :pipeline_id, :stage_id, :contact_id, :title,
                        :value_cents, :currency, :sort_order)
                returning id
                """
            ),
            {
                "agency_id": str(principal.agency_id),
                "pipeline_id": str(payload.pipeline_id),
                "stage_id": str(payload.stage_id),
                "contact_id": str(payload.contact_id) if payload.contact_id else None,
                "title": payload.title,
                "value_cents": payload.value_cents,
                "currency": payload.currency,
                "sort_order": payload.sort_order,
            },
        )
        deal_id = str(result.scalar_one())

    event = EventEnvelope(
        event="crm.deal.created",
        agency_id=principal.agency_id,
        actor=Actor(type="user", id="api"),
        data={
            "deal_id": deal_id,
            "pipeline_id": str(payload.pipeline_id),
            "stage_id": str(payload.stage_id),
            "value_cents": payload.value_cents,
            "currency": payload.currency,
        },
    )
    await _publish(_bus(request), _settings(request), event)
    return {"id": deal_id}


@router.get("/deals")
async def list_deals(
    request: Request,
    principal: Principal = Depends(get_principal),
    limit: int = 50,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 200))
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                select id, pipeline_id, stage_id, title, value_cents, currency,
                       version, updated_at
                from deals
                where agency_id = :agency_id
                order by updated_at desc
                limit :limit
                """
            ),
            {"agency_id": str(principal.agency_id), "limit": limit},
        )
        rows = result.mappings().all()
    return [
        {
            "id": str(r["id"]),
            "pipeline_id": str(r["pipeline_id"]),
            "stage_id": str(r["stage_id"]),
            "title": r["title"],
            "value_cents": r["value_cents"],
            "currency": r["currency"],
            "version": r["version"],
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


@router.patch("/deals/{deal_id}/move")
async def move_deal(deal_id: UUID, payload: DealMove, request: Request) -> dict[str, Any]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                update deals
                set stage_id = :stage_id,
                    sort_order = :sort_order,
                    version = version + 1,
                    updated_at = now()
                where id = :id and version = :version
                returning id, agency_id, pipeline_id, stage_id, version
                """
            ),
            {
                "id": str(deal_id),
                "stage_id": str(payload.stage_id),
                "sort_order": payload.sort_order,
                "version": payload.version,
            },
        )
        row = result.mappings().first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="deal version mismatch — refresh and retry",
        )

    event = EventEnvelope(
        event="crm.deal.moved",
        agency_id=row["agency_id"],
        actor=Actor(type="user", id="api"),
        data={
            "deal_id": str(row["id"]),
            "pipeline_id": str(row["pipeline_id"]),
            "stage_id": str(row["stage_id"]),
            "version": row["version"],
        },
    )
    await _publish(_bus(request), _settings(request), event)
    return {"id": str(row["id"]), "version": row["version"]}
