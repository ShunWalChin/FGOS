from __future__ import annotations

import json
import secrets
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from core_engine import repository as repo
from core_engine.bus import RedisStreamBus
from core_engine.db import session_scope
from core_engine.events import Actor, EventEnvelope
from core_engine.providers.registry import SUPPORTED_PLATFORMS, oauth_authorize_url
from core_engine.settings import Settings

router = APIRouter(prefix="/api", tags=["social"])


class SocialAccountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agency_id: UUID
    platform: str
    external_account_id: str = Field(min_length=1)
    access_token: str = Field(min_length=1)
    refresh_token: str | None = None
    scopes: list[str] = Field(default_factory=list)
    client_id: UUID | None = None
    expires_at: datetime | None = None


class PostIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agency_id: UUID
    social_account_id: UUID
    caption: str = ""
    media_urls: list[str] = Field(default_factory=list)
    scheduled_at: datetime


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _bus(request: Request) -> RedisStreamBus:
    return request.app.state.bus


def _factory(request: Request):
    return request.app.state.session_factory


def _check_platform(platform: str) -> None:
    if platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported platform; use one of {SUPPORTED_PLATFORMS}",
        )


@router.post("/social-accounts", status_code=status.HTTP_201_CREATED)
async def connect_account(payload: SocialAccountIn, request: Request) -> dict[str, str]:
    _check_platform(payload.platform)
    settings = _settings(request)
    async with session_scope(_factory(request)) as session:
        account_id = await repo.insert_social_account(
            session,
            agency_id=str(payload.agency_id),
            platform=payload.platform,
            external_account_id=payload.external_account_id,
            access_token=payload.access_token,
            encryption_key=settings.token_encryption_key,
            client_id=str(payload.client_id) if payload.client_id else None,
            refresh_token=payload.refresh_token,
            expires_at=payload.expires_at.isoformat() if payload.expires_at else None,
            scopes=payload.scopes,
        )

    await _bus(request).publish(settings.stream_events, EventEnvelope(
        event="social.account.connected",
        agency_id=payload.agency_id,
        actor=Actor(type="user", id="api"),
        data={"social_account_id": account_id, "platform": payload.platform},
    ))
    return {"id": account_id}


@router.get("/social-accounts")
async def list_accounts(request: Request, agency_id: UUID) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        rows = await repo.list_social_accounts(session, agency_id=str(agency_id))
    return [_jsonable(r) for r in rows]


@router.post("/posts", status_code=status.HTTP_201_CREATED)
async def schedule_post(payload: PostIn, request: Request) -> dict[str, str]:
    settings = _settings(request)
    body = {"caption": payload.caption, "media_urls": payload.media_urls}
    async with session_scope(_factory(request)) as session:
        post_id = await repo.enqueue_post(
            session,
            agency_id=str(payload.agency_id),
            social_account_id=str(payload.social_account_id),
            payload=json.dumps(body, ensure_ascii=True),
            scheduled_at=payload.scheduled_at.isoformat(),
        )

    await _bus(request).publish(settings.stream_events, EventEnvelope(
        event="social.post.scheduled",
        agency_id=payload.agency_id,
        actor=Actor(type="user", id="api"),
        data={
            "post_id": post_id,
            "social_account_id": str(payload.social_account_id),
            "scheduled_at": payload.scheduled_at.isoformat(),
        },
    ))
    return {"id": post_id}


@router.get("/posts")
async def list_scheduled_posts(
    request: Request, agency_id: UUID, limit: int = 50
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 200))
    async with session_scope(_factory(request)) as session:
        rows = await repo.list_posts(session, agency_id=str(agency_id), limit=limit)
    return [_jsonable(r) for r in rows]


@router.get("/oauth/{platform}/authorize")
async def oauth_authorize(platform: str, request: Request, agency_id: UUID) -> dict[str, str]:
    """Return the provider consent URL. `state` carries the tenant so the
    callback can attribute the account; store it server-side in production."""

    _check_platform(platform)
    settings = _settings(request)
    state = f"{agency_id}:{secrets.token_urlsafe(16)}"
    return {"authorize_url": oauth_authorize_url(platform, state, settings), "state": state}


@router.get("/oauth/{platform}/callback")
async def oauth_callback(
    platform: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
) -> dict[str, str]:
    """OAuth redirect target. With SOCIAL_LIVE=false this only echoes the grant
    (no token exchange) so the flow is inspectable end-to-end without a real app.
    Live mode exchanges `code` for tokens and calls insert_social_account."""

    _check_platform(platform)
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing code")
    settings = _settings(request)
    if not settings.social_live:
        return {
            "status": "dry-run",
            "platform": platform,
            "code": code,
            "state": state or "",
            "note": "SOCIAL_LIVE=false — token exchange skipped",
        }
    # Live token exchange plugs in here (httpx POST to the platform token endpoint),
    # then repo.insert_social_account(...) with the encrypted tokens.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="live token exchange not implemented for this platform yet",
    )


def _jsonable(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if hasattr(value, "isoformat"):
            out[key] = value.isoformat()
        elif hasattr(value, "hex") and not isinstance(value, (bytes, bytearray)):
            out[key] = str(value)
        else:
            out[key] = value
    return out
