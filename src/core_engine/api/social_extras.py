"""Social content library — captions + media (Module B extension, absorbed from Stackposts).

Reusable captions and a folder-based media library that feed the social scheduler. Original FGOS
implementation; multi-tenant by agency_id.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from core_engine.api.deps import Principal, get_principal
from core_engine.db import session_scope

router = APIRouter(prefix="/api", tags=["social-content"])


class CaptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class MediaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    is_folder: bool = False
    parent_id: UUID | None = None
    url: str | None = None
    mime: str | None = None


def _factory(request: Request):
    return request.app.state.session_factory


# --------------------------------------------------------------------------- captions
@router.get("/captions")
async def list_captions(
    request: Request, principal: Principal = Depends(get_principal)
) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text("select id, title, content, created_at from captions "
                     "where agency_id = :a order by created_at desc"),
                {"a": str(principal.agency_id)},
            )
        ).mappings().all()
    return [
        {"id": str(r["id"]), "title": r["title"], "content": r["content"],
         "created_at": r["created_at"].isoformat()}
        for r in rows
    ]


@router.post("/captions", status_code=status.HTTP_201_CREATED)
async def create_caption(
    payload: CaptionIn, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        result = await session.execute(
            text("insert into captions(agency_id, title, content) values (:a, :t, :c) returning id"),
            {"a": str(principal.agency_id), "t": payload.title, "c": payload.content},
        )
        return {"id": str(result.scalar_one())}


# --------------------------------------------------------------------------- media library
@router.get("/media")
async def list_media(
    request: Request, parent_id: UUID | None = None,
    principal: Principal = Depends(get_principal),
) -> list[dict[str, Any]]:
    clause = "parent_id = :p" if parent_id else "parent_id is null"
    params: dict[str, Any] = {"a": str(principal.agency_id)}
    if parent_id:
        params["p"] = str(parent_id)
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text(
                    f"select id, parent_id, is_folder, name, url, mime, size_bytes "
                    f"from media_files where agency_id = :a and {clause} "
                    f"order by is_folder desc, name"
                ),
                params,
            )
        ).mappings().all()
    return [
        {"id": str(r["id"]), "parent_id": str(r["parent_id"]) if r["parent_id"] else None,
         "is_folder": r["is_folder"], "name": r["name"], "url": r["url"], "mime": r["mime"],
         "size_bytes": r["size_bytes"]}
        for r in rows
    ]


@router.post("/media", status_code=status.HTTP_201_CREATED)
async def create_media(
    payload: MediaIn, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        if payload.parent_id is not None:
            owns = await session.execute(
                text("select 1 from media_files where id = :p and agency_id = :a and is_folder = true"),
                {"p": str(payload.parent_id), "a": str(principal.agency_id)},
            )
            if owns.first() is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parent folder not found")
        result = await session.execute(
            text(
                "insert into media_files(agency_id, parent_id, is_folder, name, url, mime) "
                "values (:a, :p, :f, :n, :u, :m) returning id"
            ),
            {"a": str(principal.agency_id),
             "p": str(payload.parent_id) if payload.parent_id else None,
             "f": payload.is_folder, "n": payload.name, "u": payload.url, "m": payload.mime},
        )
        return {"id": str(result.scalar_one())}
