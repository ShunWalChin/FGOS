from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from core_engine import repository as repo
from core_engine.api.deps import Principal, get_principal
from core_engine.auth import create_token, hash_password, verify_password
from core_engine.db import session_scope
from core_engine.settings import Settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agency_id: str
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=6, max_length=200)
    full_name: str | None = None
    role: str = "member"


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    password: str


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _factory(request: Request):
    return request.app.state.session_factory


def _issue(settings: Settings, user: dict[str, Any]) -> dict[str, Any]:
    token = create_token(
        {
            "sub": user["id"],
            "agency_id": user["agency_id"],
            "email": user["email"],
            "role": user.get("role", "member"),
        },
        settings.auth_secret,
        ttl_seconds=settings.access_token_ttl_seconds,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.access_token_ttl_seconds,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "agency_id": user["agency_id"],
            "role": user.get("role", "member"),
            "full_name": user.get("full_name"),
        },
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterIn, request: Request) -> dict[str, Any]:
    settings = _settings(request)
    async with session_scope(_factory(request)) as session:
        user_id = await repo.create_user(
            session,
            agency_id=payload.agency_id,
            email=str(payload.email),
            password_hash=hash_password(payload.password),
            full_name=payload.full_name,
            role=payload.role,
        )
    user = {
        "id": user_id,
        "agency_id": payload.agency_id,
        "email": str(payload.email),
        "role": payload.role,
        "full_name": payload.full_name,
    }
    return _issue(settings, user)


@router.post("/login")
async def login(payload: LoginIn, request: Request) -> dict[str, Any]:
    settings = _settings(request)
    async with session_scope(_factory(request)) as session:
        user = await repo.get_user_by_email(session, email=str(payload.email))

    if not user or not user.get("password_hash") or not verify_password(
        payload.password, user["password_hash"]
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )
    return _issue(settings, user)


@router.get("/me")
async def me(principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    return {
        "user_id": principal.user_id,
        "agency_id": str(principal.agency_id),
        "email": principal.email,
        "role": principal.role,
    }
