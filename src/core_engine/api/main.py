from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core_engine.api.atendimento import router as atendimento_router
from core_engine.api.audit import router as audit_router
from core_engine.api.auth import router as auth_router
from core_engine.api.bi import router as bi_router
from core_engine.api.campaigns import router as campaigns_router
from core_engine.api.chat import router as chat_router
from core_engine.api.growth import router as growth_router
from core_engine.api.crm import router as crm_router
from core_engine.api.ingest import router as ingest_router
from core_engine.api.onboarding import router as onboarding_router
from core_engine.api.social import router as social_router
from core_engine.api.social_extras import router as social_extras_router
from core_engine.api.voice import router as voice_router
from core_engine.api.workspaces import router as workspaces_router
from core_engine.bus import RedisStreamBus
from core_engine.db import create_session_factory
from core_engine.settings import Settings, get_settings


def build_app(settings: Settings | None = None, bus: RedisStreamBus | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings or get_settings()
        app.state.bus = bus or RedisStreamBus.from_url(app.state.settings.redis_url)
        app.state.owns_bus = bus is None
        app.state.session_factory = create_session_factory(app.state.settings.database_url)
        try:
            yield
        finally:
            if app.state.owns_bus:
                await app.state.bus.close()

    app = FastAPI(
        title="FGOS API",
        version="0.2.0",
        description="FAT Tech Growth Operacional System — event-driven backend.",
        lifespan=lifespan,
    )

    resolved = settings or get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in resolved.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(onboarding_router)
    app.include_router(ingest_router)
    app.include_router(workspaces_router)
    app.include_router(crm_router)
    app.include_router(social_router)
    app.include_router(social_extras_router)
    app.include_router(voice_router)
    app.include_router(growth_router)
    app.include_router(audit_router)
    app.include_router(chat_router)
    app.include_router(atendimento_router)
    app.include_router(campaigns_router)
    app.include_router(bi_router)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "fgos"}

    @app.get("/api/ping", tags=["system"])
    async def ping() -> dict[str, str]:
        return {"pong": "true"}

    # BI dashboard (ECharts) — served if the directory is present.
    if os.path.isdir("dashboard"):
        app.mount("/dashboard", StaticFiles(directory="dashboard", html=True), name="dashboard")

    # White-label onboarding shell (self-service signup).
    if os.path.isdir("onboarding"):
        app.mount("/onboarding", StaticFiles(directory="onboarding", html=True), name="onboarding")

    return app


app = build_app()
