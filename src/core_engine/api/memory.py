"""Semantic memory / RAG API (Module Memória) — original FGOS rewrite of RuVector's core.

Ingest text → chunk → embed (feature-hash, offline) → store dense vector (pgvector) + sparse tsvector.
Search runs BOTH a dense (cosine) and a sparse (full-text) ranking and fuses them with Reciprocal
Rank Fusion — the hybrid retrieval RuVector champions. Multi-tenant by agency_id.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from core_engine.api.deps import Principal, get_principal
from core_engine.db import session_scope
from core_engine.providers.embeddings import chunk_text, embed, rrf_fuse, to_pgvector

router = APIRouter(prefix="/api/memory", tags=["memory"])
CANDIDATES = 20  # per-signal candidate pool before fusion


class IngestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = "note"
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)


class SearchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1)
    k: int = 6


def _factory(request: Request):
    return request.app.state.session_factory


@router.get("/documents")
async def list_documents(
    request: Request, principal: Principal = Depends(get_principal)
) -> list[dict[str, Any]]:
    async with session_scope(_factory(request)) as session:
        rows = (
            await session.execute(
                text(
                    """
                    select d.id, d.kind, d.title, d.created_at,
                           (select count(*) from memory_chunks c where c.document_id = d.id) as chunks
                    from memory_documents d where d.agency_id = :a order by d.created_at desc
                    """
                ),
                {"a": str(principal.agency_id)},
            )
        ).mappings().all()
    return [
        {"id": str(r["id"]), "kind": r["kind"], "title": r["title"], "chunks": r["chunks"],
         "created_at": r["created_at"].isoformat()}
        for r in rows
    ]


@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest(
    payload: IngestIn, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, Any]:
    chunks = chunk_text(payload.content)
    async with session_scope(_factory(request)) as session:
        doc_id = str((await session.execute(
            text("insert into memory_documents(agency_id, kind, title, content) "
                 "values (:a, :k, :t, :c) returning id"),
            {"a": str(principal.agency_id), "k": payload.kind, "t": payload.title, "c": payload.content},
        )).scalar_one())
        for i, ch in enumerate(chunks):
            await session.execute(
                text(
                    "insert into memory_chunks(agency_id, document_id, chunk_index, content, embedding) "
                    "values (:a, :d, :i, :c, cast(:e as vector))"
                ),
                {"a": str(principal.agency_id), "d": doc_id, "i": i, "c": ch, "e": to_pgvector(embed(ch))},
            )
    return {"id": doc_id, "chunks": len(chunks)}


@router.post("/search")
async def search(
    payload: SearchIn, request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, Any]:
    k = max(1, min(payload.k, 20))
    qvec = to_pgvector(embed(payload.query))
    a = str(principal.agency_id)
    async with session_scope(_factory(request)) as session:
        dense = [str(r[0]) for r in (await session.execute(
            text("select id from memory_chunks where agency_id = :a and embedding is not null "
                 "order by embedding <=> cast(:qv as vector) limit :n"),
            {"a": a, "qv": qvec, "n": CANDIDATES},
        )).all()]
        sparse = [str(r[0]) for r in (await session.execute(
            text("select id from memory_chunks where agency_id = :a "
                 "and tsv @@ plainto_tsquery('portuguese', :q) "
                 "order by ts_rank(tsv, plainto_tsquery('portuguese', :q)) desc limit :n"),
            {"a": a, "q": payload.query, "n": CANDIDATES},
        )).all()]

        fused = rrf_fuse(dense, sparse)[:k]
        if not fused:
            return {"hits": [], "dense": len(dense), "sparse": len(sparse)}

        rows = (await session.execute(
            text(
                """
                select c.id, c.content, c.document_id, d.title, d.kind
                from memory_chunks c join memory_documents d on d.id = c.document_id
                where c.id::text = any(:ids)
                """
            ),
            {"ids": fused},
        )).mappings().all()

    by_id = {str(r["id"]): r for r in rows}
    dense_set, sparse_set = set(dense), set(sparse)
    hits = []
    for rank, cid in enumerate(fused):
        r = by_id.get(cid)
        if not r:
            continue
        signals = [s for s, present in (("dense", cid in dense_set), ("sparse", cid in sparse_set)) if present]
        hits.append({
            "chunk_id": cid, "document_id": str(r["document_id"]), "title": r["title"],
            "kind": r["kind"], "rank": rank + 1, "signals": signals,
            "snippet": r["content"][:240],
        })
    return {"hits": hits, "dense": len(dense), "sparse": len(sparse)}


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID, request: Request, principal: Principal = Depends(get_principal)
) -> None:
    async with session_scope(_factory(request)) as session:
        res = await session.execute(
            text("delete from memory_documents where id = :id and agency_id = :a"),
            {"id": str(document_id), "a": str(principal.agency_id)},
        )
        if res.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
