from __future__ import annotations

import json
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from core_engine import repository as repo
from core_engine.api.deps import Principal, get_principal
from core_engine.auth import create_token, hash_password
from core_engine.db import session_scope
from core_engine.events import Actor, EventEnvelope
from core_engine.settings import Settings
from core_engine.slug import DEFAULT_BRANDING, merge_branding, slugify

router = APIRouter(prefix="/api", tags=["onboarding"])


class SignupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agency_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=6, max_length=200)
    owner_name: str | None = None
    slug: str | None = None
    branding: dict[str, str] | None = None


class BrandingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branding: dict[str, str]


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _factory(request: Request):
    return request.app.state.session_factory


async def _unique_slug(session, desired: str) -> str:
    base = slugify(desired)
    slug = base
    while await repo.slug_exists(session, slug=slug):
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


@router.get("/onboarding/check-slug")
async def check_slug(request: Request, slug: str) -> dict[str, Any]:
    normalized = slugify(slug)
    async with session_scope(_factory(request)) as session:
        taken = await repo.slug_exists(session, slug=normalized)
    return {"slug": normalized, "available": not taken}


@router.post("/onboarding/signup", status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupIn, request: Request) -> dict[str, Any]:
    settings = _settings(request)
    branding = merge_branding({**(payload.branding or {}), "display_name": payload.agency_name})

    async with session_scope(_factory(request)) as session:
        slug = await _unique_slug(session, payload.slug or payload.agency_name)
        provisioned = await repo.create_agency_with_owner(
            session,
            agency_name=payload.agency_name,
            slug=slug,
            owner_email=payload.email,
            owner_password_hash=hash_password(payload.password),
            branding_json=json.dumps(branding, ensure_ascii=True),
            owner_name=payload.owner_name,
        )

    # auto-login: the new owner gets a token immediately
    token = create_token(
        {
            "sub": provisioned["user_id"],
            "agency_id": provisioned["agency_id"],
            "email": payload.email,
            "role": "owner",
        },
        settings.auth_secret,
        ttl_seconds=settings.access_token_ttl_seconds,
    )

    event = EventEnvelope(
        event="agency.provisioned",
        agency_id=provisioned["agency_id"],
        actor=Actor(type="user", id="onboarding"),
        data={"slug": slug, "plan": "trial", "owner_email": payload.email},
    )
    await request.app.state.bus.publish(settings.stream_events, event)

    return {
        "access_token": token,
        "token_type": "bearer",
        "agency": {"id": provisioned["agency_id"], "slug": slug, "name": payload.agency_name},
        "branding": branding,
        "dashboard_url": f"/dashboard/?agency_id={provisioned['agency_id']}",
    }


@router.get("/agencies/{slug}/branding")
async def public_branding(slug: str, request: Request) -> dict[str, Any]:
    """Public endpoint — lets the white-label shell theme itself by tenant."""
    async with session_scope(_factory(request)) as session:
        agency = await repo.get_branding_by_slug(session, slug=slugify(slug))
    if not agency:
        # graceful default so an unknown slug still renders the FAT Tech shell
        return {"slug": slug, "name": "FGOS", "branding": dict(DEFAULT_BRANDING), "found": False}
    return {
        "id": agency["id"],
        "slug": agency["slug"],
        "name": agency["name"],
        "plan": agency.get("plan"),
        "branding": merge_branding(agency.get("branding")),
        "found": True,
    }


@router.patch("/agencies/branding")
async def update_branding(
    payload: BrandingIn,
    request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    merged = merge_branding(payload.branding)
    async with session_scope(_factory(request)) as session:
        ok = await repo.update_branding(
            session,
            agency_id=str(principal.agency_id),
            branding_json=json.dumps(merged, ensure_ascii=True),
        )
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="agency not found")
    return {"branding": merged}
