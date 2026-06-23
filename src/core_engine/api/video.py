"""Video projects API (Module Vídeo) — absorbed from OpenCut.

FGOS tracks the video project (optionally linked to a generated content piece); the editing happens
in OpenCut, a companion web editor opened via editor_url. Original FGOS implementation, multi-tenant.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from core_engine.api.deps import Principal, get_principal
from core_engine.db import session_scope

router = APIRouter(prefix="/api", tags=["video"])

DEFAULT_EDITOR = "https://opencut.app"
VALID_STATUS = {"draft", "editing", "rendered"}


class VideoProjectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    content_piece_id: UUID | None = None
    editor_url: str | None = None


class VideoProjectPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


def _factory(request: Request):
    return request.app.state.session_factory


@router.get("/video-projects")
async def list_projects(
    request: Request, principal: Principal = Depends(get_principal)
) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text("select id, name, content_piece_id, editor_url, status, created_at "
                     "from video_projects where agency_id = :a order by created_at desc"),
                {"a": str(principal.agency_id)},
            )
        ).mappings().all()
    return [
        {"id": str(r["id"]), "name": r["name"],
         "content_piece_id": str(r["content_piece_id"]) if r["content_piece_id"] else None,
         "editor_url": r["editor_url"] or DEFAULT_EDITOR, "status": r["status"],
         "created_at": r["created_at"].isoformat()}
        for r in rows
    ]


@router.post("/video-projects", status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: VideoProjectIn, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        if payload.content_piece_id is not None:
            owns = await session.execute(
                text("select 1 from content_pieces where id = :c and agency_id = :a"),
                {"c": str(payload.content_piece_id), "a": str(principal.agency_id)},
            )
            if owns.first() is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="content_piece not found")
        result = await session.execute(
            text(
                "insert into video_projects(agency_id, name, content_piece_id, editor_url) "
                "values (:a, :n, :c, :e) returning id"
            ),
            {"a": str(principal.agency_id), "n": payload.name,
             "c": str(payload.content_piece_id) if payload.content_piece_id else None,
             "e": payload.editor_url or DEFAULT_EDITOR},
        )
        return {"id": str(result.scalar_one())}


@router.patch("/video-projects/{project_id}")
async def update_project(
    project_id: UUID, payload: VideoProjectPatch, request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, str]:
    if payload.status not in VALID_STATUS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid status")
    async with session_scope(_factory(request)) as session:
        row = (await session.execute(
            text("update video_projects set status = :s where id = :id and agency_id = :a returning status"),
            {"s": payload.status, "id": str(project_id), "a": str(principal.agency_id)},
        )).first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return {"id": str(project_id), "status": row[0]}


@router.delete("/video-projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID, request: Request, principal: Principal = Depends(get_principal)
) -> None:
    async with session_scope(_factory(request)) as session:
        res = await session.execute(
            text("delete from video_projects where id = :id and agency_id = :a"),
            {"id": str(project_id), "a": str(principal.agency_id)},
        )
        if res.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
