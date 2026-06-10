from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core_engine.api.main import build_app
from core_engine.auth import create_token
from core_engine.settings import Settings

SECRET = "test-secret"
AGENCY_A = "aaaaaaaa-0000-0000-0000-000000000001"
AGENCY_B = "bbbbbbbb-0000-0000-0000-000000000002"


def _mock_session_factory(rows=None):
    rows = rows or []
    mapping_mock = MagicMock()
    mapping_mock.all = MagicMock(return_value=rows)
    execute_result = MagicMock()
    execute_result.mappings = MagicMock(return_value=mapping_mock)
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=execute_result)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=mock_ctx)


def _token(agency_id: str) -> str:
    return create_token(
        {"sub": "user-1", "agency_id": agency_id, "role": "owner", "email": "u@test.com"},
        SECRET,
        ttl_seconds=3600,
    )


@pytest.fixture
def app():
    settings = Settings(
        auth_required=True,
        auth_secret=SECRET,
        database_url="postgresql+asyncpg://x:x@localhost/x",
        redis_url="redis://localhost:6379/0",
    )
    bus = AsyncMock()
    bus.redis = AsyncMock()
    with patch("core_engine.api.main.create_session_factory", return_value=_mock_session_factory()):
        return build_app(settings=settings, bus=bus)


@pytest.mark.asyncio
async def test_workspace_list_uses_token_agency_id(app):
    """agency_id from query string is ignored; endpoint uses token's agency_id."""
    token = _token(AGENCY_A)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/workspaces",
            params={"agency_id": AGENCY_B},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_deals_list_uses_token_agency_id(app):
    """agency_id from query string is ignored; endpoint uses token's agency_id."""
    token = _token(AGENCY_A)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/deals",
            params={"agency_id": AGENCY_B},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected(app):
    """No token + auth_required=True → 401 before any DB query."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/workspaces")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_contacts_use_token_agency_id(app):
    """Contacts endpoint no longer accepts agency_id as query param."""
    token = _token(AGENCY_A)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/contacts",
            params={"agency_id": AGENCY_B},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json() == []
