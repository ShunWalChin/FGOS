from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status

from core_engine.bus import RedisStreamBus
from core_engine.events import Actor, EventEnvelope
from core_engine.security import valid_meta_signature
from core_engine.settings import Settings

router = APIRouter(tags=["ingest"])


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _bus(request: Request) -> RedisStreamBus:
    return request.app.state.bus


@router.get("/webhooks/meta")
async def verify_meta_webhook(request: Request) -> Response:
    settings = _settings(request)
    query = request.query_params

    if (
        query.get("hub.mode") == "subscribe"
        and query.get("hub.verify_token") == settings.meta_verify_token
        and query.get("hub.challenge")
    ):
        return Response(content=query["hub.challenge"], media_type="text/plain")

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


@router.post("/webhooks/meta")
async def receive_meta_webhook(request: Request) -> Response:
    settings = _settings(request)
    raw_body = await request.body()
    signature = request.headers.get("x-hub-signature-256")

    if not valid_meta_signature(raw_body, signature, settings.meta_app_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    payload = _decode_json(raw_body)
    event = EventEnvelope(
        event="webhook.meta.received",
        agency_id=settings.default_agency_id,
        actor=Actor(type="webhook", id="meta"),
        data={"payload": payload},
    )

    await _bus(request).publish(settings.stream_webhooks_meta, event)
    return Response(status_code=status.HTTP_200_OK)


def _decode_json(raw_body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"raw": raw_body.decode("utf-8", errors="replace")}
    return value if isinstance(value, dict) else {"value": value}
