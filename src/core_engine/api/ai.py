"""AI / LLM models panel API (Module IA).

Per-agency LLM connections with API keys encrypted at rest (pgcrypto). List never exposes keys;
`test` makes a real round-trip to the provider to validate the key. Wiring: worker-content resolves
the agency's default model for live generation. Original FGOS implementation, multi-tenant.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from core_engine.api.deps import Principal, get_principal
from core_engine.db import session_scope
from core_engine.providers.llm import ChatTurn
from core_engine.providers.llm_live import PROVIDERS, make_provider
from core_engine.settings import Settings

router = APIRouter(prefix="/api", tags=["ai"])

SUGGESTED: dict[str, list[str]] = {
    "openai": ["gpt-4o", "gpt-4o-mini", "o1-mini"],
    "anthropic": ["claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5"],
    "google": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash"],
    "groq": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
    "mistral": ["mistral-large-latest", "mistral-small-latest"],
    "openrouter": ["openai/gpt-4o", "anthropic/claude-sonnet-4-5"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "together": ["meta-llama/Llama-3.3-70B-Instruct-Turbo"],
    "xai": ["grok-2-latest"],
}


class AIModelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    label: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=120)
    api_key: str = Field(min_length=1)
    base_url: str | None = None
    make_default: bool = False


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _factory(request: Request):
    return request.app.state.session_factory


@router.get("/ai-models/providers")
async def providers() -> dict[str, Any]:
    return {"providers": PROVIDERS, "suggested": SUGGESTED}


@router.get("/ai-models")
async def list_models(
    request: Request, principal: Principal = Depends(get_principal)
) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text(
                    "select id, provider, label, model, base_url, is_default, status, last_error, "
                    "(api_key_enc is not null) as has_key, created_at "
                    "from ai_models where agency_id = :a order by is_default desc, created_at desc"
                ),
                {"a": str(principal.agency_id)},
            )
        ).mappings().all()
    return [
        {"id": str(r["id"]), "provider": r["provider"], "label": r["label"], "model": r["model"],
         "base_url": r["base_url"], "is_default": r["is_default"], "status": r["status"],
         "last_error": r["last_error"], "has_key": r["has_key"], "created_at": r["created_at"].isoformat()}
        for r in rows
    ]


@router.post("/ai-models", status_code=status.HTTP_201_CREATED)
async def create_model(
    payload: AIModelIn, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, str]:
    if payload.provider.lower() not in PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"provider must be one of {PROVIDERS}")
    key = _settings(request).token_encryption_key
    async with session_scope(_factory(request)) as session:
        is_first = (await session.execute(
            text("select count(*) from ai_models where agency_id = :a"), {"a": str(principal.agency_id)}
        )).scalar_one() == 0
        make_default = payload.make_default or is_first
        if make_default:
            await session.execute(
                text("update ai_models set is_default = false where agency_id = :a"),
                {"a": str(principal.agency_id)},
            )
        result = await session.execute(
            text(
                """
                insert into ai_models(agency_id, provider, label, model, base_url, api_key_enc, is_default)
                values (:a, :p, :l, :m, :b, pgp_sym_encrypt(cast(:k as text), :ek), :d)
                returning id
                """
            ),
            {"a": str(principal.agency_id), "p": payload.provider.lower(), "l": payload.label,
             "m": payload.model, "b": payload.base_url, "k": payload.api_key, "ek": key, "d": make_default},
        )
        return {"id": str(result.scalar_one())}


@router.patch("/ai-models/{model_id}/default")
async def set_default(
    model_id: UUID, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        owns = await session.execute(
            text("select 1 from ai_models where id = :id and agency_id = :a"),
            {"id": str(model_id), "a": str(principal.agency_id)},
        )
        if owns.first() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await session.execute(text("update ai_models set is_default = false where agency_id = :a"), {"a": str(principal.agency_id)})
        await session.execute(text("update ai_models set is_default = true where id = :id"), {"id": str(model_id)})
    return {"id": str(model_id), "is_default": "true"}


@router.delete("/ai-models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(
    model_id: UUID, request: Request, principal: Principal = Depends(get_principal)
) -> None:
    async with session_scope(_factory(request)) as session:
        res = await session.execute(
            text("delete from ai_models where id = :id and agency_id = :a"),
            {"id": str(model_id), "a": str(principal.agency_id)},
        )
        if res.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


@router.post("/ai-models/{model_id}/test")
async def test_model(
    model_id: UUID, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, Any]:
    """Real round-trip to the provider with the decrypted key. Updates status accordingly."""
    key = _settings(request).token_encryption_key
    async with session_scope(_factory(request)) as session:
        row = (await session.execute(
            text("select provider, model, base_url, pgp_sym_decrypt(api_key_enc, :k) as api_key "
                 "from ai_models where id = :id and agency_id = :a"),
            {"id": str(model_id), "a": str(principal.agency_id), "k": key},
        )).mappings().first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    ok, detail = False, ""
    try:
        provider = make_provider(row["provider"], row["api_key"] or "", row["model"], row["base_url"])
        reply = await provider.complete(system="You are a connectivity test.", history=[], user="ping")
        ok, detail = True, (reply.text or "")[:120]
    except Exception as exc:  # provider/auth/network error — surfaced honestly
        detail = str(exc)[:200]

    async with session_scope(_factory(request)) as session:
        await session.execute(
            text("update ai_models set status = :s, last_error = :e where id = :id and agency_id = :a"),
            {"s": "active" if ok else "error", "e": None if ok else detail,
             "id": str(model_id), "a": str(principal.agency_id)},
        )
    return {"ok": ok, "detail": detail}


# re-export ChatTurn so callers can build histories without importing two modules
__all__ = ["router", "ChatTurn"]
