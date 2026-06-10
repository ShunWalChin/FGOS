from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core_engine.api.main import build_app
from core_engine.auth import create_token
from core_engine.settings import Settings

SECRET = "test-secret"
AGENCY_A = "00000000-0000-0000-0000-000000000001"


def _mock_session_factory():
    mock_session = AsyncMock()
    execute_result = MagicMock()
    execute_result.mappings.return_value.first.return_value = None
    mock_session.execute = AsyncMock(return_value=execute_result)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=mock_ctx)


def _make_settings(**overrides) -> Settings:
    base = dict(
        auth_required=True,
        auth_secret=SECRET,
        database_url="postgresql+asyncpg://x:x@localhost/x",
        redis_url="redis://localhost:6379/0",
    )
    base.update(overrides)
    return Settings(**base)


def _make_bus():
    bus = AsyncMock()
    bus.redis = AsyncMock()
    bus.redis.incr = AsyncMock(return_value=1)
    bus.redis.expire = AsyncMock(return_value=True)
    return bus


@pytest.fixture
def auth_app():
    settings = _make_settings(auth_required=True)
    bus = _make_bus()
    with patch("core_engine.api.main.create_session_factory", return_value=_mock_session_factory()):
        return build_app(settings=settings, bus=bus)


@pytest.fixture
def noauth_app():
    settings = _make_settings(auth_required=False)
    bus = _make_bus()
    with patch("core_engine.api.main.create_session_factory", return_value=_mock_session_factory()):
        return build_app(settings=settings, bus=bus)


@pytest.mark.asyncio
async def test_login_missing_credentials(auth_app):
    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://test") as client:
        resp = await client.post("/api/auth/login", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_me_without_token_rejected_when_auth_required(auth_app):
    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://test") as client:
        resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_without_token_allowed_when_auth_disabled(noauth_app):
    async with AsyncClient(transport=ASGITransport(app=noauth_app), base_url="http://test") as client:
        resp = await client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["role"] == "dev"


@pytest.mark.asyncio
async def test_me_with_valid_token(auth_app):
    token = create_token(
        {"sub": "user-1", "agency_id": AGENCY_A, "email": "test@test.com", "role": "owner"},
        SECRET,
        ttl_seconds=3600,
    )
    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://test") as client:
        resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "owner"
    assert data["agency_id"] == AGENCY_A
