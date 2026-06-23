"""Voice agents API (Module Voz) — absorbed from fat-tech-voz-panel.

A voice agent binds an agency to a conversational voice front-end (ElevenLabs Convai agent_id).
Original FGOS implementation; multi-tenant by agency_id; tokens/ids scoped to the caller.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from core_engine.api.deps import Principal, get_principal
from core_engine.db import session_scope

router = APIRouter(prefix="/api", tags=["voice"])


class VoiceAgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(min_length=1, max_length=200)
    provider: str = "elevenlabs"


def _factory(request: Request):
    return request.app.state.session_factory


@router.get("/voice-agents")
async def list_voice_agents(
    request: Request, principal: Principal = Depends(get_principal)
) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text(
                    "select id, name, provider, agent_id, status, created_at "
                    "from voice_agents where agency_id = :a order by created_at desc"
                ),
                {"a": str(principal.agency_id)},
            )
        ).mappings().all()
    return [
        {"id": str(r["id"]), "name": r["name"], "provider": r["provider"],
         "agent_id": r["agent_id"], "status": r["status"],
         "created_at": r["created_at"].isoformat()}
        for r in rows
    ]


@router.post("/voice-agents", status_code=status.HTTP_201_CREATED)
async def create_voice_agent(
    payload: VoiceAgentIn, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                "insert into voice_agents(agency_id, name, provider, agent_id) "
                "values (:a, :n, :p, :ag) returning id"
            ),
            {"a": str(principal.agency_id), "n": payload.name, "p": payload.provider, "ag": payload.agent_id},
        )
        return {"id": str(result.scalar_one())}


@router.delete("/voice-agents/{agent_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voice_agent(
    agent_uuid: UUID, request: Request, principal: Principal = Depends(get_principal)
) -> None:
    async with session_scope(_factory(request)) as session:
        res = await session.execute(
            text("delete from voice_agents where id = :id and agency_id = :a"),
            {"id": str(agent_uuid), "a": str(principal.agency_id)},
        )
        if res.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
