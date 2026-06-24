from __future__ import annotations

import math
import re
from dataclasses import dataclass


TOKEN_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9_]{3,}")


@dataclass(frozen=True)
class Chunk:
    id: str
    title: str
    text: str
    source: str = ""


@dataclass(frozen=True)
class SearchHit:
    chunk: Chunk
    score: float


def tokenize(text: str) -> set[str]:
    return {m.group(0).lower() for m in TOKEN_RE.finditer(text)}


def chunk_text(text: str, *, max_chars: int = 900, overlap: int = 120) -> list[str]:
    clean = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not clean:
        return []
    chunks: list[str] = []
    i = 0
    while i < len(clean):
        end = min(len(clean), i + max_chars)
        if end < len(clean):
            boundary = clean.rfind(".", i, end)
            if boundary > i + max_chars // 2:
                end = boundary + 1
        chunks.append(clean[i:end].strip())
        if end >= len(clean):
            break
        i = max(0, end - overlap)
    return [c for c in chunks if c]


def bm25_like(query: str, chunks: list[Chunk], *, k: int = 5) -> list[SearchHit]:
    q_tokens = tokenize(query)
    if not q_tokens:
        return []
    docs = [tokenize(chunk.text) for chunk in chunks]
    n_docs = max(1, len(docs))
    document_frequency: dict[str, int] = {}
    for tokens in docs:
        for token in tokens:
            document_frequency[token] = document_frequency.get(token, 0) + 1

    hits: list[SearchHit] = []
    for chunk, tokens in zip(chunks, docs):
        if not tokens:
            continue
        overlap = q_tokens & tokens
        if not overlap:
            continue
        score = 0.0
        for token in overlap:
            idf = math.log((n_docs + 1) / (document_frequency.get(token, 0) + 0.5))
            score += max(0.1, idf)
        score = score / math.sqrt(len(tokens))
        hits.append(SearchHit(chunk=chunk, score=round(score, 4)))
    return sorted(hits, key=lambda hit: hit.score, reverse=True)[:k]


def build_context(hits: list[SearchHit], *, max_chars: int = 2400) -> str:
    parts: list[str] = []
    used = 0
    for hit in hits:
        block = f"[{hit.chunk.title} | score={hit.score}]\n{hit.chunk.text}"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n\n---\n\n".join(parts)

