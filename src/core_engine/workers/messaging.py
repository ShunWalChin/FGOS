from __future__ import annotations

import asyncio
import json
import time

from sqlalchemy.ext.asyncio import AsyncSession

from core_engine.ai.guardrails import evaluate_guardrails
from core_engine import repository as repo
from core_engine.bus import RedisStreamBus
from core_engine.db import create_session_factory, session_scope
from core_engine.events import Actor, EventEnvelope
from core_engine.messaging.flow import DEFAULT_FLOW, advance
from core_engine.providers.llm import ChatTurn, get_llm
from core_engine.providers.messenger import get_messenger
from core_engine.providers.meta import extract_inbound_message
from core_engine.settings import Settings, get_settings
from core_engine.workers.runtime import run_stream_worker

DEBOUNCE_ZSET = "debounce:messaging"
SYSTEM_PROMPT = (
    "Você é um assistente de atendimento de uma agência de marketing brasileira. "
    "Responda em PT-BR, de forma curta, cordial e objetiva."
)


# --- inbound: persist + debounce -----------------------------------------


async def handle_meta_message(
    event: EventEnvelope,
    session: AsyncSession,
    bus: RedisStreamBus,
    settings: Settings,
) -> None:
    if event.event != "webhook.meta.received":
        return

    inbound = extract_inbound_message(event.data.get("payload", {}))
    if not inbound:
        return

    contact_id = await repo.upsert_contact(
        session,
        agency_id=str(event.agency_id),
        channel=inbound["channel"],
        sender=inbound["sender"],
    )
    chat = await repo.get_or_create_session(
        session,
        agency_id=str(event.agency_id),
        contact_id=contact_id,
        channel=inbound["channel"],
    )
    chat_session_id = str(chat["id"])

    message_id = await repo.insert_message(
        session,
        session_id=chat_session_id,
        direction="in",
        body=inbound["text"],
        provider_msg_id=inbound["provider_message_id"] or None,
    )
    if message_id is None:
        return  # duplicate webhook — already stored

    await bus.publish(settings.stream_events, EventEnvelope(
        event="messaging.message.inbound",
        agency_id=event.agency_id,
        actor=Actor(type="webhook", id="meta"),
        data={"session_id": chat_session_id, "contact_id": contact_id, "text": inbound["text"]},
    ))

    # debounce: buffer by the real session id, (re)arm the flush timer
    await bus.add_to_debounce(f"buf:messaging:{chat_session_id}", inbound["text"], ttl_seconds=60)
    await bus.redis.zadd(
        DEBOUNCE_ZSET,
        {chat_session_id: time.time() + settings.messaging_debounce_seconds},
    )


# --- flush: state machine + AI + outbound --------------------------------


async def flush_due_buffers(
    bus: RedisStreamBus,
    session_factory,
    settings: Settings | None = None,
) -> list[dict[str, str]]:
    settings = settings or get_settings()
    now = time.time()
    due = await bus.redis.zrangebyscore(DEBOUNCE_ZSET, min=0, max=now)
    flushed: list[dict[str, str]] = []

    for raw in due:
        session_id = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        await bus.redis.zrem(DEBOUNCE_ZSET, session_id)
        parts = await bus.drain_list(f"buf:messaging:{session_id}")
        if not parts:
            continue
        consolidated = "\n".join(parts)
        async with session_scope(session_factory) as db:
            await _respond(db, bus, settings, session_id, consolidated)
        flushed.append({"session_id": session_id, "text": consolidated})

    return flushed


async def _respond(
    db: AsyncSession,
    bus: RedisStreamBus,
    settings: Settings,
    session_id: str,
    text: str,
) -> None:
    chat = await repo.get_session(db, session_id=session_id)
    if not chat:
        return

    # Live-chat takeover: a human is driving — the bot stays silent.
    if chat.get("mode") == "human":
        return

    agency_id = str(chat["agency_id"])
    decision = advance(DEFAULT_FLOW, chat.get("current_node_id"), chat.get("context") or {}, text)

    replies = list(decision.replies)
    if decision.use_ai:
        llm = get_llm(settings)
        history = [ChatTurn(role="user", content=text)]
        reply = await llm.complete(system=SYSTEM_PROMPT, history=history, user=text)
        replies.append(reply.text)

    messenger = get_messenger(chat["channel"], settings)
    guardrail_handoff = False
    for body in replies:
        guardrail = evaluate_guardrails(user_text=text, assistant_text=body)
        if guardrail.action == "block":
            body = "Vou encaminhar seu atendimento para uma pessoa da equipe para seguir com segurança."
            guardrail_handoff = True
        elif guardrail.action == "handoff":
            guardrail_handoff = True
        send = await messenger.send(to=chat["contact_id"], text=body)
        await repo.insert_message(
            db, session_id=session_id, direction="out", body=body,
            provider_msg_id=send.provider_msg_id,
        )
        await bus.publish(settings.stream_events, EventEnvelope(
            event="messaging.message.outbound",
            agency_id=agency_id,
            actor=Actor(type="system", id="worker-messaging"),
            data={"session_id": session_id, "text": body, "ai": decision.use_ai},
        ))

    await repo.update_session_state(
        db,
        session_id=session_id,
        current_node_id=decision.next_node_id,
        context=json.dumps(decision.context_updates, ensure_ascii=True),
    )

    if decision.handoff or guardrail_handoff:
        await repo.set_session_mode(db, session_id=session_id, mode="human")
        await bus.publish(settings.stream_events, EventEnvelope(
            event="messaging.session.handoff",
            agency_id=agency_id,
            actor=Actor(type="system", id="worker-messaging"),
            data={"session_id": session_id, "contact_id": chat["contact_id"]},
        ))


async def run_message_buffer_flusher(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    bus = RedisStreamBus.from_url(settings.redis_url)
    session_factory = create_session_factory(settings.database_url)
    try:
        while True:
            await flush_due_buffers(bus, session_factory, settings)
            await asyncio.sleep(0.5)
    finally:
        await bus.close()


async def run(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    await run_stream_worker(
        stream=settings.stream_webhooks_meta,
        handler=handle_meta_message,
        settings=settings,
        worker_role="messaging",
    )
