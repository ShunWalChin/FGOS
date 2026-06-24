from __future__ import annotations

from dataclasses import dataclass

from core_engine.ai.rag import Chunk, bm25_like


@dataclass(frozen=True)
class VaultNote:
    id: str
    kind: str
    title: str
    body: str
    tags: list[str]


def search_notes(query: str, notes: list[VaultNote], *, k: int = 8):
    chunks = [
        Chunk(
            id=note.id,
            title=f"{note.kind}: {note.title}",
            text=f"{note.body}\nTags: {', '.join(note.tags)}",
        )
        for note in notes
    ]
    return bm25_like(query, chunks, k=k)


def suggest_kind(body: str) -> str:
    low = body.lower()
    if any(word in low for word in ("decidimos", "decisão", "adr", "porque")):
        return "decision"
    if any(word in low for word in ("cuidado", "evitar", "bug", "risco", "falha")):
        return "pitfall"
    if any(word in low for word in ("passo", "rodar", "comando", "workflow", "metodologia")):
        return "methodology"
    return "note"

