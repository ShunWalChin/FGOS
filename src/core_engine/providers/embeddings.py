"""Embeddings — deterministic, offline-first (feature hashing), with a live extension point.

RuVector emphasises dense+sparse hybrid retrieval. Here the dense side uses a signed feature-hashing
embedding: deterministic, no network, and similar texts (shared tokens) land near each other in
cosine space — enough to drive a real hybrid search offline. Swapping in a provider embedding model
(OpenAI text-embedding-3-small → 1536 dims) is a drop-in: keep DIM and return its vector.
"""

from __future__ import annotations

import hashlib
import math
import re

DIM = 1536
_token_re = re.compile(r"[0-9a-zà-ú]{2,}", re.IGNORECASE)


def _tokens(text: str) -> list[str]:
    return _token_re.findall(text.lower())


def embed(text: str, dim: int = DIM) -> list[float]:
    """Signed feature-hashing embedding, L2-normalised."""
    vec = [0.0] * dim
    for tok in _tokens(text):
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 17) & 1 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def to_pgvector(vec: list[float]) -> str:
    """Serialise to pgvector literal: '[v1,v2,...]'."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def rrf_fuse(*ranked_lists: list[str], k: int = 60) -> list[str]:
    """Reciprocal Rank Fusion (RuVector's hybrid fusion) over id lists. Higher = better."""
    scores: dict[str, float] = {}
    for ids in ranked_lists:
        for rank, cid in enumerate(ids):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda c: -scores[c])


def chunk_text(text: str, *, max_chars: int = 600) -> list[str]:
    """Split into chunks on paragraph boundaries, capped at max_chars."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras or [text.strip()]:
        if len(buf) + len(p) + 1 <= max_chars:
            buf = f"{buf}\n{p}".strip()
        else:
            if buf:
                chunks.append(buf)
            buf = p[:max_chars]
    if buf:
        chunks.append(buf)
    return chunks or [text.strip()[:max_chars]]
