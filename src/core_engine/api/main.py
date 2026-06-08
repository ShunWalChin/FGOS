from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from core_engine.api.crm import router as crm_router
from core_engine.api.ingest import router as ingest_router
from core_engine.api.social import router as social_router
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
        title="Core-Engine",
        version="0.1.0",
        description="Python event-driven backbone for marketing agency operations.",
        lifespan=lifespan,
    )

    app.include_router(ingest_router)
    app.include_router(workspaces_router)
    app.include_router(crm_router)
    app.include_router(social_router)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "core-engine"}

    @app.get("/api/ping", tags=["system"])
    async def ping() -> dict[str, str]:
        return {"pong": "true"}

    return app


app = build_app()
