"""Content generation worker (Growth) — turns a 'requested' content piece into a brand-voice-aware
draft. Dry-run by default (templated, no network); when MESSAGING_LLM_LIVE + LLM_API_KEY are set the
live branch would call the LLM provider. Anti-slop is applied to the output.

Absorbed from fat-tech-growthOS (brand voice + content creation). Same FOR UPDATE SKIP LOCKED + poll
pattern as the campaigns/social workers; emits growth.content.generated on the bus (mirrored to BI).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import text

from core_engine.bus import RedisStreamBus
from core_engine.db import create_session_factory, session_scope
from core_engine.events import Actor, EventEnvelope
from core_engine.providers.llm_live import resolve_agency_provider
from core_engine.settings import Settings, get_settings

logger = logging.getLogger(__name__)

DEFAULT_BANNED = [
    "game-changer", "revolutionary", "cutting-edge", "best-in-class", "synergy", "leverage",
    "disrupt", "disruptivo", "revolucionário", "inovador", "transform your", "unlock the power",
]


def _as_list(v: Any) -> list[str]:
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except json.JSONDecodeError:
            return []
    return [str(x) for x in v] if isinstance(v, list) else []


def _strip_banned(textval: str, banned: list[str]) -> str:
    out = textval
    for b in banned:
        if b and b.lower() in out.lower():
            # soft-remove: drop the cliché token rather than the sentence
            out = out.replace(b, "").replace(b.capitalize(), "")
    return " ".join(out.split())


def _generate_draft(piece: dict[str, Any], brand: dict[str, Any] | None) -> str:
    """Deterministic, brand-aware dry-run draft. (Live mode would call the LLM here.)"""
    name = (brand or {}).get("name") or "a marca"
    tone = _as_list((brand or {}).get("tone")) if brand else []
    tone_str = ", ".join(tone) if tone else "claro e direto"
    prompt = (piece.get("prompt") or piece.get("title") or "").strip()
    ptype = piece.get("type") or "copy"
    platform = piece.get("platform") or "geral"

    if ptype == "carousel":
        body = (
            f"[{name} · carrossel para {platform}]\n"
            f"Capa: {prompt}\n"
            f"Slide 1 — o problema que seu público vive hoje.\n"
            f"Slide 2 — a virada (com um número concreto).\n"
            f"Slide 3 — como a {name} resolve, passo a passo.\n"
            f"Slide 4 — prova/resultado.\n"
            f"CTA: chame a {name} no link da bio."
        )
    elif ptype == "video_brief":
        body = (
            f"[{name} · brief de vídeo · {platform}]\n"
            f"Tema: {prompt}\n"
            f"Hook (3s): pergunta direta ao público.\n"
            f"Desenvolvimento: 2-3 pontos com exemplos reais.\n"
            f"Fechamento: CTA + assinatura {name}.\n"
            f"Tom: {tone_str}."
        )
    elif ptype == "seo":
        body = (
            f"# {prompt}\n\n"
            f"Intro objetiva respondendo a intenção de busca.\n"
            f"## Pontos principais\n- ...\n- ...\n## Conclusão\nCTA para a {name}.\n"
            f"(tom {tone_str})"
        )
    else:  # copy / sales_page
        body = (
            f"{prompt}\n\n"
            f"A {name} ajuda você a sair de onde está para onde quer chegar — com método, não com sorte.\n"
            f"Sem promessa vazia: o próximo passo é simples. Fale com a gente.\n"
            f"(tom: {tone_str})"
        )

    banned = list(DEFAULT_BANNED) + (_as_list((brand or {}).get("avoid")) if brand else [])
    return _strip_banned(body, banned)


async def _publish(bus: RedisStreamBus, settings: Settings, event: EventEnvelope) -> None:
    await bus.publish(settings.stream_events, event)


async def _claim_and_generate(session, bus: RedisStreamBus, settings: Settings) -> bool:
    row = (
        await session.execute(
            text(
                """
                select id, agency_id, brand_voice_id, type, platform, title, prompt
                from content_pieces
                where status = 'requested'
                order by created_at
                for update skip locked limit 1
                """
            )
        )
    ).mappings().first()
    if not row:
        return False

    brand = None
    if row["brand_voice_id"]:
        brand = (
            await session.execute(
                text("select name, tone, avoid from brand_voices where id = :b"),
                {"b": str(row["brand_voice_id"])},
            )
        ).mappings().first()
        brand = dict(brand) if brand else None

    body = _generate_draft(dict(row), brand)   # dry-run fallback
    model_used = "dry-run"
    try:
        provider = await resolve_agency_provider(session, str(row["agency_id"]), settings.token_encryption_key)
        if provider is not None:
            tone = ", ".join(_as_list((brand or {}).get("tone"))) if brand else "claro e direto"
            avoid = ", ".join(_as_list((brand or {}).get("avoid"))) if brand else ""
            sysmsg = (
                f"Você é redator da marca {(brand or {}).get('name') or 'FAT Tech'}. "
                f"Tom: {tone}. Evite clichês como: {avoid or 'disruptivo, revolucionário'}. "
                f"Produza um {row['type']} para {row['platform'] or 'redes sociais'}, "
                f"em português, pronto para publicar."
            )
            reply = await provider.complete(system=sysmsg, history=[], user=row["prompt"] or row["title"])
            if reply.text.strip():
                body = reply.text.strip()
                model_used = reply.model
    except Exception:
        logger.exception("live LLM generation failed; falling back to dry-run draft")

    banned = list(DEFAULT_BANNED) + (_as_list((brand or {}).get("avoid")) if brand else [])
    body = _strip_banned(body, banned)
    await session.execute(
        text("update content_pieces set body = :b, status = 'draft', model = :m, updated_at = now() where id = :id"),
        {"b": body, "m": model_used, "id": str(row["id"])},
    )
    await _publish(bus, settings, EventEnvelope(
        event="growth.content.generated",
        agency_id=row["agency_id"],
        actor=Actor(type="system", id="worker-content"),
        data={"content_id": str(row["id"]), "type": row["type"], "model": model_used},
    ))
    logger.info("content generated", extra={"content_id": str(row["id"]), "type": row["type"]})
    return True


async def run(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    session_factory = create_session_factory(settings.database_url)
    bus = RedisStreamBus.from_url(settings.redis_url)
    logger.info("content worker started")
    try:
        while True:
            async with session_scope(session_factory) as session:
                did = await _claim_and_generate(session, bus, settings)
            if not did:
                await asyncio.sleep(2)
    finally:
        await bus.close()
