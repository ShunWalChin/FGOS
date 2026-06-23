"""Audit / AI Console API (Module Auditoria, kairos-style).

Observability over the event bus: an event feed from ClickHouse `events_log`, a trace viewer that
reconstructs an event chain by `trace_id` (the canonical envelope's lineage), and the ticket
lifecycle audit from Postgres `ticket_traking`. Read-only; multi-tenant by agency_id.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text

from core_engine.api.deps import Principal, get_principal
from core_engine.clickhouse_client import create_clickhouse_client
from core_engine.db import session_scope
from core_engine.settings import Settings

router = APIRouter(prefix="/api/audit", tags=["audit"])


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _factory(request: Request):
    return request.app.state.session_factory


def _client(request: Request):
    client = getattr(request.app.state, "clickhouse", None)
    if client is None:
        client = create_clickhouse_client(_settings(request).clickhouse_dsn)
        request.app.state.clickhouse = client
    return client


def _query(request: Request, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    result = _client(request).query(sql, parameters=params)
    cols = result.column_names
    return [_jsonable(dict(zip(cols, row))) for row in result.result_rows]


def _jsonable(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        out[k] = v.isoformat() if hasattr(v, "isoformat") else v
    return out


@router.get("/events")
async def list_events(
    request: Request,
    principal: Principal = Depends(get_principal),
    event_type: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Recent events for the agency (live feed)."""
    limit = max(1, min(limit, 500))
    sql = (
        "select occurred_at, event_type, entity_id, trace_id, hops, event_id, meta "
        "from events_log where agency_id = {a:String}"
    )
    params: dict[str, Any] = {"a": str(principal.agency_id), "l": limit}
    if event_type:
        sql += " and event_type like {q:String}"
        params["q"] = f"%{event_type}%"
    sql += " order by occurred_at desc limit {l:UInt32}"
    return _query(request, sql, params)


@router.get("/trace/{trace_id}")
async def trace(
    trace_id: str, request: Request, principal: Principal = Depends(get_principal)
) -> list[dict[str, Any]]:
    """Reconstruct a full event chain by trace_id, ordered by hop then time."""
    sql = (
        "select occurred_at, event_type, entity_id, hops, event_id, meta "
        "from events_log where agency_id = {a:String} and trace_id = {t:String} "
        "order by hops, occurred_at"
    )
    return _query(request, sql, {"a": str(principal.agency_id), "t": trace_id})


@router.get("/tickets")
async def ticket_audit(
    request: Request, principal: Principal = Depends(get_principal), limit: int = 100
) -> list[dict[str, Any]]:
    """Ticket lifecycle audit trail from Postgres ticket_traking."""
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text(
                    """
                    select tt.ticket_id, tt.action, tt.detail, tt.created_at,
                           coalesce(c.full_name, c.phone, c.email, 'Contato') as contact
                    from ticket_traking tt
                    join tickets t on t.id = tt.ticket_id
                    join contacts c on c.id = t.contact_id
                    where tt.agency_id = :a
                    order by tt.created_at desc limit :l
                    """
                ),
                {"a": str(principal.agency_id), "l": max(1, min(limit, 300))},
            )
        ).mappings().all()
    return [
        {"ticket_id": str(r["ticket_id"]), "action": r["action"], "detail": r["detail"],
         "contact": r["contact"], "at": r["created_at"].isoformat()}
        for r in rows
    ]
