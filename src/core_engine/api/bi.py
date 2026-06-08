from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request

from core_engine import bi_queries
from core_engine.clickhouse_client import create_clickhouse_client
from core_engine.settings import Settings

router = APIRouter(prefix="/api/bi", tags=["bi"])


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _client(request: Request):
    """Lazily create and cache a ClickHouse client on app.state."""
    client = getattr(request.app.state, "clickhouse", None)
    if client is None:
        client = create_clickhouse_client(_settings(request).clickhouse_dsn)
        request.app.state.clickhouse = client
    return client


def _run(request: Request, builder, *args) -> list[dict[str, Any]]:
    sql, params = builder(*args)
    result = _client(request).query(sql, parameters=params)
    cols = result.column_names
    return [dict(zip(cols, row)) for row in result.result_rows]


@router.get("/summary")
async def summary(request: Request, agency_id: UUID) -> dict[str, Any]:
    rows = _run(request, bi_queries.summary_query, str(agency_id))
    return rows[0] if rows else {}


@router.get("/timeseries")
async def timeseries(request: Request, agency_id: UUID, days: int = 30) -> list[dict[str, Any]]:
    return _run(request, bi_queries.timeseries_query, str(agency_id), days)


@router.get("/breakdown")
async def breakdown(request: Request, agency_id: UUID, limit: int = 20) -> list[dict[str, Any]]:
    return _run(request, bi_queries.breakdown_query, str(agency_id), limit)


@router.get("/funnel")
async def funnel(request: Request, agency_id: UUID) -> list[dict[str, Any]]:
    return _run(request, bi_queries.funnel_query, str(agency_id))


@router.get("/health")
async def bi_health(request: Request) -> dict[str, str]:
    try:
        _client(request).query("select 1")
        return {"clickhouse": "ok"}
    except Exception as exc:  # pragma: no cover - depends on live CH
        return {"clickhouse": "down", "error": str(exc)[:200]}
