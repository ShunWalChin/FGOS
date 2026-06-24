from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from core_engine.ai.governance import GovernanceInput, evaluate_governance
from core_engine.ai.guardrails import GuardrailPolicy, evaluate_guardrails
from core_engine.ai.llm_bridge import build_messages, create_client
from core_engine.ai.rag import Chunk, bm25_like, build_context, chunk_text, tokenize
from core_engine.ai.scoring import score_lead
from core_engine.ai.vault import VaultNote, search_notes, suggest_kind
from core_engine.api.deps import Principal, get_principal
from core_engine.bus import RedisStreamBus
from core_engine.db import session_scope
from core_engine.events import Actor, EventEnvelope
from core_engine.settings import Settings

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])
logger = logging.getLogger(__name__)


class CompleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system: str = ""
    user: str = Field(min_length=1)
    history: list[dict[str, str]] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None


class GuardrailPolicyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    rules: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class GuardrailEvalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_text: str = Field(min_length=1)
    assistant_text: str = ""
    surface: str = "general"
    policy_id: UUID | None = None


class KnowledgeBaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None


class KnowledgeDocumentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1)
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagQueryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=12)
    answer: bool = False


class GovernanceEvalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(min_length=1, max_length=240)
    regime: str = "semi"
    confidence: float = Field(default=0.7, ge=0, le=1)
    impact: str = "medium"
    reversible: bool = True
    user_text: str = ""
    assistant_text: str = ""


class LeadScoreIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deal_id: UUID | None = None
    title: str = ""
    notes: str = ""
    value_cents: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    apply: bool = True


class VaultNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str | None = None
    title: str = Field(min_length=1, max_length=220)
    body: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


def _factory(request: Request):
    return request.app.state.session_factory


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _bus(request: Request) -> RedisStreamBus:
    return request.app.state.bus


async def _publish(request: Request, event: EventEnvelope) -> None:
    try:
        await _bus(request).publish(_settings(request).stream_events, event)
    except Exception as exc:  # pragma: no cover - depends on live Redis/Docker
        logger.warning("intelligence event publish skipped: %s", exc)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True)


def _guardrail_response(decision) -> dict[str, Any]:
    return {
        "allowed": decision.allowed,
        "action": decision.action,
        "risk_score": decision.risk_score,
        "findings": [
            {"code": item.code, "severity": item.severity, "message": item.message}
            for item in decision.findings
        ],
    }


async def _load_policy(session, agency_id: UUID, policy_id: UUID | None = None) -> tuple[str | None, GuardrailPolicy]:
    if policy_id is not None:
        row = (
            await session.execute(
                text(
                    """
                    select id, name, rules
                    from ai_guardrail_policies
                    where agency_id = :a and id = :id
                    """
                ),
                {"a": str(agency_id), "id": str(policy_id)},
            )
        ).mappings().first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="policy not found")
        rules = row["rules"] if isinstance(row["rules"], dict) else json.loads(row["rules"] or "{}")
        rules.setdefault("name", row["name"])
        return str(row["id"]), GuardrailPolicy.from_payload(rules)

    row = (
        await session.execute(
            text(
                """
                select id, name, rules
                from ai_guardrail_policies
                where agency_id = :a and active
                order by updated_at desc
                limit 1
                """
            ),
            {"a": str(agency_id)},
        )
    ).mappings().first()
    if row is None:
        return None, GuardrailPolicy()
    rules = row["rules"] if isinstance(row["rules"], dict) else json.loads(row["rules"] or "{}")
    rules.setdefault("name", row["name"])
    return str(row["id"]), GuardrailPolicy.from_payload(rules)


@router.get("/tools")
async def tools(request: Request, principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    async with session_scope(_factory(request)) as session:
        row = (
            await session.execute(
                text(
                    """
                    select
                      (select count(*) from ai_guardrail_policies where agency_id = :a) as policies,
                      (select count(*) from knowledge_bases where agency_id = :a) as knowledge_bases,
                      (select count(*) from ai_governance_audits where agency_id = :a) as audits,
                      (select count(*) from lead_score_history where agency_id = :a) as lead_scores,
                      (select count(*) from ai_vault_notes where agency_id = :a) as vault_notes
                    """
                ),
                {"a": str(principal.agency_id)},
            )
        ).mappings().one()
    return {
        "tools": [
            {"id": "llm_bridge", "name": "LLM Bridge", "status": "ready"},
            {"id": "guardrails", "name": "Guardrails", "status": "ready", "count": row["policies"]},
            {"id": "rag", "name": "RAG por agência", "status": "ready", "count": row["knowledge_bases"]},
            {"id": "governance", "name": "Governança IA", "status": "ready", "count": row["audits"]},
            {"id": "lead_scoring", "name": "BANT / Lead score", "status": "ready", "count": row["lead_scores"]},
            {"id": "vault", "name": "Vault operacional", "status": "ready", "count": row["vault_notes"]},
        ]
    }


@router.post("/llm/complete")
async def complete(
    payload: CompleteIn,
    request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    settings = _settings(request)
    client = create_client(
        provider=payload.provider or settings.llm_provider,
        model=payload.model or settings.llm_model,
        api_key=settings.llm_api_key,
        live=settings.messaging_llm_live,
        base_url=settings.llm_base_url,
    )
    result = await client.chat(
        build_messages(system=payload.system, history=payload.history, user=payload.user),
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
    await _publish(
        request,
        EventEnvelope(
            event="ai.llm.completed",
            agency_id=principal.agency_id,
            actor=Actor(type="user", id=principal.user_id or "api"),
            data={"provider": result.provider, "model": result.model, "dry_run": result.dry_run},
        ),
    )
    return {
        "text": result.text,
        "provider": result.provider,
        "model": result.model,
        "dry_run": result.dry_run,
        "tokens": result.total_tokens,
        "latency_ms": result.latency_ms,
    }


@router.get("/guardrails/policies")
async def list_policies(
    request: Request,
    principal: Principal = Depends(get_principal),
) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text(
                    """
                    select id, name, rules, active, updated_at
                    from ai_guardrail_policies
                    where agency_id = :a
                    order by updated_at desc
                    """
                ),
                {"a": str(principal.agency_id)},
            )
        ).mappings().all()
    return [
        {
            "id": str(row["id"]),
            "name": row["name"],
            "rules": row["rules"],
            "active": row["active"],
            "updated_at": row["updated_at"].isoformat(),
        }
        for row in rows
    ]


@router.post("/guardrails/policies", status_code=status.HTTP_201_CREATED)
async def create_policy(
    payload: GuardrailPolicyIn,
    request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        row = (
            await session.execute(
                text(
                    """
                    insert into ai_guardrail_policies(agency_id, name, rules, active)
                    values (:a, :n, cast(:r as jsonb), :active)
                    on conflict (agency_id, name) do update
                    set rules = excluded.rules, active = excluded.active, updated_at = now()
                    returning id
                    """
                ),
                {
                    "a": str(principal.agency_id),
                    "n": payload.name,
                    "r": _json(payload.rules),
                    "active": payload.active,
                },
            )
        ).first()
    return {"id": str(row[0])}


@router.post("/guardrails/evaluate")
async def guardrail_eval(
    payload: GuardrailEvalIn,
    request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    async with session_scope(_factory(request)) as session:
        policy_id, policy = await _load_policy(session, principal.agency_id, payload.policy_id)
        decision = evaluate_guardrails(
            user_text=payload.user_text,
            assistant_text=payload.assistant_text,
            policy=policy,
        )
        await session.execute(
            text(
                """
                insert into ai_guardrail_evaluations(
                  agency_id, policy_id, surface, action, allowed, risk_score,
                  findings, input_excerpt, output_excerpt
                )
                values (:a, :p, :s, :action, :allowed, :risk, cast(:f as jsonb), :i, :o)
                """
            ),
            {
                "a": str(principal.agency_id),
                "p": policy_id,
                "s": payload.surface,
                "action": decision.action,
                "allowed": decision.allowed,
                "risk": decision.risk_score,
                "f": _json(_guardrail_response(decision)["findings"]),
                "i": payload.user_text[:500],
                "o": payload.assistant_text[:500],
            },
        )
    await _publish(
        request,
        EventEnvelope(
            event="ai.guardrail.evaluated",
            agency_id=principal.agency_id,
            actor=Actor(type="user", id=principal.user_id or "api"),
            data={"surface": payload.surface, "action": decision.action, "risk_score": decision.risk_score},
        ),
    )
    return _guardrail_response(decision)


@router.get("/knowledge-bases")
async def list_knowledge_bases(
    request: Request,
    principal: Principal = Depends(get_principal),
) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text(
                    """
                    select kb.id, kb.name, kb.description, kb.status, kb.updated_at,
                           count(distinct d.id) as documents,
                           count(c.id) as chunks
                    from knowledge_bases kb
                    left join knowledge_documents d on d.knowledge_base_id = kb.id
                    left join knowledge_chunks c on c.knowledge_base_id = kb.id
                    where kb.agency_id = :a
                    group by kb.id
                    order by kb.updated_at desc
                    """
                ),
                {"a": str(principal.agency_id)},
            )
        ).mappings().all()
    return [
        {
            "id": str(row["id"]),
            "name": row["name"],
            "description": row["description"],
            "status": row["status"],
            "documents": row["documents"],
            "chunks": row["chunks"],
            "updated_at": row["updated_at"].isoformat(),
        }
        for row in rows
    ]


@router.post("/knowledge-bases", status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    payload: KnowledgeBaseIn,
    request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, str]:
    async with session_scope(_factory(request)) as session:
        row = (
            await session.execute(
                text(
                    """
                    insert into knowledge_bases(agency_id, name, description)
                    values (:a, :n, :d)
                    on conflict (agency_id, name) do update
                    set description = excluded.description, updated_at = now()
                    returning id
                    """
                ),
                {"a": str(principal.agency_id), "n": payload.name, "d": payload.description},
            )
        ).first()
    return {"id": str(row[0])}


@router.post("/knowledge-bases/{base_id}/documents", status_code=status.HTTP_201_CREATED)
async def add_document(
    base_id: UUID,
    payload: KnowledgeDocumentIn,
    request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    settings = _settings(request)
    async with session_scope(_factory(request)) as session:
        owns = (
            await session.execute(
                text("select 1 from knowledge_bases where id = :id and agency_id = :a"),
                {"id": str(base_id), "a": str(principal.agency_id)},
            )
        ).first()
        if owns is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="knowledge base not found")
        row = (
            await session.execute(
                text(
                    """
                    insert into knowledge_documents(
                      agency_id, knowledge_base_id, title, source, body, metadata
                    )
                    values (:a, :kb, :t, :s, :b, cast(:m as jsonb))
                    returning id
                    """
                ),
                {
                    "a": str(principal.agency_id),
                    "kb": str(base_id),
                    "t": payload.title,
                    "s": payload.source,
                    "b": payload.body,
                    "m": _json(payload.metadata),
                },
            )
        ).first()
        document_id = str(row[0])
        chunks = chunk_text(
            payload.body,
            max_chars=settings.rag_chunk_chars,
            overlap=settings.rag_chunk_overlap,
        )
        for idx, body in enumerate(chunks):
            await session.execute(
                text(
                    """
                    insert into knowledge_chunks(
                      agency_id, knowledge_base_id, document_id, chunk_index, title, body, tokens
                    )
                    values (:a, :kb, :d, :idx, :t, :b, :tokens)
                    """
                ),
                {
                    "a": str(principal.agency_id),
                    "kb": str(base_id),
                    "d": document_id,
                    "idx": idx,
                    "t": payload.title,
                    "b": body,
                    "tokens": list(tokenize(body)),
                },
            )
        await session.execute(
            text("update knowledge_bases set updated_at = now() where id = :id"),
            {"id": str(base_id)},
        )
    return {"id": document_id, "chunks": len(chunks)}


@router.post("/knowledge-bases/{base_id}/query")
async def query_knowledge_base(
    base_id: UUID,
    payload: RagQueryIn,
    request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text(
                    """
                    select id, title, body
                    from knowledge_chunks
                    where agency_id = :a and knowledge_base_id = :kb
                    order by created_at desc
                    limit 1000
                    """
                ),
                {"a": str(principal.agency_id), "kb": str(base_id)},
            )
        ).mappings().all()
    chunks = [Chunk(id=str(row["id"]), title=row["title"], text=row["body"]) for row in rows]
    hits = bm25_like(payload.question, chunks, k=payload.k)
    context = build_context(hits)
    answer = None
    if payload.answer:
        settings = _settings(request)
        client = create_client(
            provider=settings.llm_provider,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            live=settings.messaging_llm_live,
            base_url=settings.llm_base_url,
        )
        result = await client.chat(
            build_messages(
                system="Responda em PT-BR usando apenas o contexto. Se faltar base, diga isso.",
                history=[],
                user=f"Contexto:\n{context}\n\nPergunta: {payload.question}",
            ),
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        answer = result.text
    await _publish(
        request,
        EventEnvelope(
            event="ai.rag.queried",
            agency_id=principal.agency_id,
            actor=Actor(type="user", id=principal.user_id or "api"),
            data={"knowledge_base_id": str(base_id), "hits": len(hits), "answered": answer is not None},
        ),
    )
    return {
        "hits": [
            {"id": hit.chunk.id, "title": hit.chunk.title, "score": hit.score, "body": hit.chunk.text}
            for hit in hits
        ],
        "context": context,
        "answer": answer,
    }


@router.post("/governance/evaluate")
async def governance_eval(
    payload: GovernanceEvalIn,
    request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    guardrail = evaluate_guardrails(user_text=payload.user_text, assistant_text=payload.assistant_text)
    decision = evaluate_governance(
        GovernanceInput(
            action=payload.action,
            regime=payload.regime,
            confidence=payload.confidence,
            impact=payload.impact,
            reversible=payload.reversible,
            guardrail=guardrail,
        )
    )
    async with session_scope(_factory(request)) as session:
        await session.execute(
            text(
                """
                insert into ai_governance_audits(
                  agency_id, action, regime, status, risk_score,
                  required_approval, reason, payload
                )
                values (:a, :action, :regime, :status, :risk, :approval, :reason, cast(:payload as jsonb))
                """
            ),
            {
                "a": str(principal.agency_id),
                "action": payload.action,
                "regime": payload.regime,
                "status": decision.status,
                "risk": decision.risk_score,
                "approval": decision.required_approval,
                "reason": decision.reason,
                "payload": _json(payload.model_dump()),
            },
        )
    await _publish(
        request,
        EventEnvelope(
            event="ai.governance.evaluated",
            agency_id=principal.agency_id,
            actor=Actor(type="user", id=principal.user_id or "api"),
            data={"action": payload.action, "status": decision.status, "risk_score": decision.risk_score},
        ),
    )
    return {
        "status": decision.status,
        "reason": decision.reason,
        "required_approval": decision.required_approval,
        "risk_score": decision.risk_score,
        "regime_description": decision.regime_description,
        "guardrail": _guardrail_response(guardrail),
    }


@router.get("/governance/audits")
async def list_governance_audits(
    request: Request,
    principal: Principal = Depends(get_principal),
    limit: int = 25,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 100))
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text(
                    """
                    select action, regime, status, risk_score, reason, created_at
                    from ai_governance_audits
                    where agency_id = :a
                    order by created_at desc
                    limit :limit
                    """
                ),
                {"a": str(principal.agency_id), "limit": limit},
            )
        ).mappings().all()
    return [
        {
            "action": row["action"],
            "regime": row["regime"],
            "status": row["status"],
            "risk_score": row["risk_score"],
            "reason": row["reason"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


@router.post("/lead-score")
async def lead_score(
    payload: LeadScoreIn,
    request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    title = payload.title
    value_cents = payload.value_cents
    metadata = dict(payload.metadata)
    async with session_scope(_factory(request)) as session:
        if payload.deal_id is not None:
            row = (
                await session.execute(
                    text(
                        """
                        select title, value_cents, ai_score
                        from deals
                        where id = :id and agency_id = :a
                        """
                    ),
                    {"id": str(payload.deal_id), "a": str(principal.agency_id)},
                )
            ).mappings().first()
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="deal not found")
            title = title or row["title"]
            value_cents = value_cents or row["value_cents"]
            if row["ai_score"]:
                metadata.update(row["ai_score"] if isinstance(row["ai_score"], dict) else {})
        result = score_lead(
            title=title,
            notes=payload.notes,
            value_cents=value_cents,
            metadata=metadata,
        )
        await session.execute(
            text(
                """
                insert into lead_score_history(
                  agency_id, deal_id, bant_score, probability, temperature,
                  next_best_action, signals, explanation
                )
                values (:a, :deal, :bant, :prob, :temp, :nba, cast(:sig as jsonb), cast(:exp as jsonb))
                """
            ),
            {
                "a": str(principal.agency_id),
                "deal": str(payload.deal_id) if payload.deal_id else None,
                "bant": result.bant_score,
                "prob": result.probability,
                "temp": result.temperature,
                "nba": result.next_best_action,
                "sig": _json(result.signals),
                "exp": _json(result.explanation),
            },
        )
        if payload.apply and payload.deal_id is not None:
            await session.execute(
                text(
                    """
                    update deals
                    set bant_score = :bant,
                        probability = :prob,
                        temperature = :temp,
                        next_best_action = :nba,
                        ai_score = cast(:score as jsonb),
                        updated_at = now()
                    where id = :id and agency_id = :a
                    """
                ),
                {
                    "id": str(payload.deal_id),
                    "a": str(principal.agency_id),
                    "bant": result.bant_score,
                    "prob": result.probability,
                    "temp": result.temperature,
                    "nba": result.next_best_action,
                    "score": _json(
                        {
                            "signals": result.signals,
                            "explanation": result.explanation,
                            "source": "fgos-ai-tools",
                        }
                    ),
                },
            )
    await _publish(
        request,
        EventEnvelope(
            event="crm.lead.scored",
            agency_id=principal.agency_id,
            actor=Actor(type="user", id=principal.user_id or "api"),
            data={
                "deal_id": str(payload.deal_id) if payload.deal_id else None,
                "bant_score": result.bant_score,
                "temperature": result.temperature,
            },
        ),
    )
    return {
        "bant_score": result.bant_score,
        "probability": result.probability,
        "temperature": result.temperature,
        "next_best_action": result.next_best_action,
        "signals": result.signals,
        "explanation": result.explanation,
    }


@router.get("/vault/notes")
async def list_vault_notes(
    request: Request,
    principal: Principal = Depends(get_principal),
    limit: int = 100,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 300))
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text(
                    """
                    select id, kind, title, body, tags, updated_at
                    from ai_vault_notes
                    where agency_id = :a
                    order by updated_at desc
                    limit :limit
                    """
                ),
                {"a": str(principal.agency_id), "limit": limit},
            )
        ).mappings().all()
    return [
        {
            "id": str(row["id"]),
            "kind": row["kind"],
            "title": row["title"],
            "body": row["body"],
            "tags": list(row["tags"] or []),
            "updated_at": row["updated_at"].isoformat(),
        }
        for row in rows
    ]


@router.post("/vault/notes", status_code=status.HTTP_201_CREATED)
async def create_vault_note(
    payload: VaultNoteIn,
    request: Request,
    principal: Principal = Depends(get_principal),
) -> dict[str, str]:
    kind = payload.kind or suggest_kind(payload.body)
    async with session_scope(_factory(request)) as session:
        row = (
            await session.execute(
                text(
                    """
                    insert into ai_vault_notes(agency_id, kind, title, body, tags, created_by)
                    values (:a, :kind, :title, :body, :tags, :user_id)
                    returning id
                    """
                ),
                {
                    "a": str(principal.agency_id),
                    "kind": kind,
                    "title": payload.title,
                    "body": payload.body,
                    "tags": payload.tags,
                    "user_id": principal.user_id,
                },
            )
        ).first()
    return {"id": str(row[0]), "kind": kind}


@router.get("/vault/search")
async def search_vault(
    request: Request,
    q: str,
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text(
                    """
                    select id, kind, title, body, tags
                    from ai_vault_notes
                    where agency_id = :a
                    order by updated_at desc
                    limit 500
                    """
                ),
                {"a": str(principal.agency_id)},
            )
        ).mappings().all()
    notes = [
        VaultNote(
            id=str(row["id"]),
            kind=row["kind"],
            title=row["title"],
            body=row["body"],
            tags=list(row["tags"] or []),
        )
        for row in rows
    ]
    hits = search_notes(q, notes)
    return {
        "hits": [
            {"id": hit.chunk.id, "title": hit.chunk.title, "score": hit.score, "body": hit.chunk.text}
            for hit in hits
        ]
    }
