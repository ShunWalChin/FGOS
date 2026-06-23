"""Growth / Conteúdo API (Module Growth) — absorbed from fat-tech-growthOS.

Brand voice configuration (tone, avoid, anti-slop, autonomy) + content pieces with a draft→approved
→published lifecycle, plus an anti-slop linter that flags banned/cliché phrases. Original FGOS
implementation; multi-tenant by agency_id.
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

router = APIRouter(prefix="/api", tags=["growth"])

# Default anti-slop list (from growthOS brand-voice.yaml). Brand voices can extend it.
DEFAULT_BANNED = [
    "game-changer", "revolutionary", "cutting-edge", "best-in-class", "synergy", "leverage",
    "disrupt", "innovative solution", "transform your", "unlock the power", "dive deep",
    "it's worth noting", "in today's fast-paced", "at the end of the day", "think outside the box",
    "move the needle", "low-hanging fruit", "paradigm shift", "holistic approach",
    "seamlessly integrate",
]
VALID_STATUS = {"draft", "approved", "published"}


# --------------------------------------------------------------------------- schemas
class BrandVoiceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    tagline: str | None = None
    tone: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    personality: str | None = None
    industry: str | None = None
    platforms: dict[str, Any] = Field(default_factory=dict)
    anti_slop: dict[str, Any] = Field(default_factory=dict)
    autonomy: str = "semi"


class ContentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand_voice_id: UUID | None = None
    type: str
    platform: str | None = None
    title: str = Field(min_length=1, max_length=300)
    body: str | None = None


class ContentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str | None = None
    body: str | None = None


class LintIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str
    brand_voice_id: UUID | None = None


def _factory(request: Request):
    return request.app.state.session_factory


def _as_list(v: Any) -> list[str]:
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except json.JSONDecodeError:
            return []
    return [str(x) for x in v] if isinstance(v, list) else []


# --------------------------------------------------------------------------- brand voices
@router.get("/brand-voices")
async def list_brand_voices(
    request: Request, principal: Principal = Depends(get_principal)
) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text("select id, name, tagline, tone, avoid, personality, industry, autonomy, created_at "
                     "from brand_voices where agency_id = :a order by created_at desc"),
                {"a": str(principal.agency_id)},
            )
        ).mappings().all()
    return [
        {"id": str(r["id"]), "name": r["name"], "tagline": r["tagline"],
         "tone": _as_list(r["tone"]), "avoid": _as_list(r["avoid"]),
         "personality": r["personality"], "industry": r["industry"], "autonomy": r["autonomy"],
         "created_at": r["created_at"].isoformat()}
        for r in rows
    ]


@router.post("/brand-voices", status_code=status.HTTP_201_CREATED)
async def create_brand_voice(
    payload: BrandVoiceIn, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text(
                """
                insert into brand_voices(agency_id, name, tagline, tone, avoid, personality,
                                         industry, platforms, anti_slop, autonomy)
                values (:a, :n, :tg, cast(:tone as jsonb), cast(:avoid as jsonb), :pe, :ind,
                        cast(:pl as jsonb), cast(:as_ as jsonb), :au)
                returning id
                """
            ),
            {"a": str(principal.agency_id), "n": payload.name, "tg": payload.tagline,
             "tone": json.dumps(payload.tone), "avoid": json.dumps(payload.avoid),
             "pe": payload.personality, "ind": payload.industry,
             "pl": json.dumps(payload.platforms), "as_": json.dumps(payload.anti_slop),
             "au": payload.autonomy},
        )
        return {"id": str(result.scalar_one())}


# --------------------------------------------------------------------------- content pieces
@router.get("/content-pieces")
async def list_content(
    request: Request, principal: Principal = Depends(get_principal), status_filter: str | None = None
) -> list[dict[str, Any]]:
    clause = "agency_id = :a"
    params: dict[str, Any] = {"a": str(principal.agency_id)}
    if status_filter in VALID_STATUS:
        clause += " and status = :st"
        params["st"] = status_filter
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text(f"select id, type, platform, title, body, status, brand_voice_id, updated_at "
                     f"from content_pieces where {clause} order by updated_at desc limit 200"),
                params,
            )
        ).mappings().all()
    return [
        {"id": str(r["id"]), "type": r["type"], "platform": r["platform"], "title": r["title"],
         "body": r["body"], "status": r["status"],
         "brand_voice_id": str(r["brand_voice_id"]) if r["brand_voice_id"] else None,
         "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None}
        for r in rows
    ]


@router.post("/content-pieces", status_code=status.HTTP_201_CREATED)
async def create_content(
    payload: ContentIn, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        if payload.brand_voice_id is not None:
            owns = await session.execute(
                text("select 1 from brand_voices where id = :b and agency_id = :a"),
                {"b": str(payload.brand_voice_id), "a": str(principal.agency_id)},
            )
            if owns.first() is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="brand_voice not found")
        result = await session.execute(
            text(
                "insert into content_pieces(agency_id, brand_voice_id, type, platform, title, body) "
                "values (:a, :b, :ty, :pl, :t, :bo) returning id"
            ),
            {"a": str(principal.agency_id),
             "b": str(payload.brand_voice_id) if payload.brand_voice_id else None,
             "ty": payload.type, "pl": payload.platform, "t": payload.title, "bo": payload.body},
        )
        return {"id": str(result.scalar_one())}


@router.patch("/content-pieces/{piece_id}")
async def update_content(
    piece_id: UUID, payload: ContentPatch, request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    if payload.status is not None and payload.status not in VALID_STATUS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid status")
    sets, params = ["updated_at = now()"], {"id": str(piece_id), "a": str(principal.agency_id)}
    if payload.status is not None:
        sets.append("status = :st"); params["st"] = payload.status
    if payload.body is not None:
        sets.append("body = :bo"); params["bo"] = payload.body
    async with session_scope(_factory(request)) as session:
        row = (await session.execute(
            text(f"update content_pieces set {', '.join(sets)} where id = :id and agency_id = :a returning status"),
            params,
        )).first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return {"id": str(piece_id), "status": row[0]}


@router.post("/content-pieces/lint")
async def lint_content(
    payload: LintIn, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, Any]:
    """Anti-slop linter: flags banned/cliché phrases (default list + the brand voice's own)."""
    banned = list(DEFAULT_BANNED)
    async with session_scope(_factory(request)) as session:
        if payload.brand_voice_id is not None:
            row = (await session.execute(
                text("select anti_slop, avoid from brand_voices where id = :b and agency_id = :a"),
                {"b": str(payload.brand_voice_id), "a": str(principal.agency_id)},
            )).mappings().first()
            if row:
                anti = row["anti_slop"]
                if isinstance(anti, str):
                    try:
                        anti = json.loads(anti)
                    except json.JSONDecodeError:
                        anti = {}
                banned += [str(x) for x in (anti or {}).get("banned_phrases", [])]
                banned += _as_list(row["avoid"])
    low = payload.body.lower()
    violations = sorted({b for b in banned if b and b.lower() in low})
    return {"ok": not violations, "violations": violations, "checked": len(set(banned))}
