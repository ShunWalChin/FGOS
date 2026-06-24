from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core_engine.ai.llm_bridge import build_messages, create_client

if TYPE_CHECKING:
    from core_engine.settings import Settings


@dataclass(frozen=True)
class LLMReply:
    text: str
    model: str
    dry_run: bool = False


@dataclass
class ChatTurn:
    role: str  # "user" | "assistant" | "system"
    content: str


class LLMProvider:
    """Boundary for chat/agent inference. Real adapters (Anthropic/OpenAI/Groq)
    subclass this; the worker only ever sees `complete(...)`.

    Keeping inference behind one method is what lets the whole messaging pipeline
    run offline (DryRunLLM) and keeps the LLM off the hot path of ingestion
    (docs/ARCHITECTURE.md §0 correção 2 — IA por API externa, nunca no box)."""

    model: str = "dry"

    async def complete(self, *, system: str, history: list[ChatTurn], user: str) -> LLMReply:
        raise NotImplementedError


@dataclass
class DryRunLLM(LLMProvider):
    """Deterministic, no-network stand-in. Echoes a canned reply so the flow,
    persistence and events are all exercisable without an API key."""

    model: str = "dry"
    canned: str = ""

    async def complete(self, *, system: str, history: list[ChatTurn], user: str) -> LLMReply:
        if self.canned:
            text = self.canned
        else:
            snippet = user.strip().splitlines()[0][:120] if user.strip() else "sua mensagem"
            text = f"(IA dry-run) Recebi: “{snippet}”. Como posso ajudar?"
        return LLMReply(text=text, model=self.model, dry_run=True)


class AnthropicLLM(LLMProvider):
    """Live adapter skeleton. Activated by MESSAGING_LLM_LIVE=true + an API key.
    The HTTP call is intentionally left as the single integration point."""

    def __init__(self, *, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def complete(self, *, system: str, history: list[ChatTurn], user: str) -> LLMReply:
        client = create_client(
            provider="anthropic",
            model=self.model,
            api_key=self.api_key,
            live=True,
        )
        result = await client.chat(
            build_messages(
                system=system,
                history=[{"role": turn.role, "content": turn.content} for turn in history],
                user=user,
            )
        )
        return LLMReply(text=result.text, model=result.model, dry_run=result.dry_run)


class BridgeLLM(LLMProvider):
    """Live adapter backed by the modular FGOS LLM bridge."""

    def __init__(self, *, provider: str, api_key: str, model: str, base_url: str = "") -> None:
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    async def complete(self, *, system: str, history: list[ChatTurn], user: str) -> LLMReply:
        client = create_client(
            provider=self.provider,
            model=self.model,
            api_key=self.api_key,
            live=True,
            base_url=self.base_url,
        )
        result = await client.chat(
            build_messages(
                system=system,
                history=[{"role": turn.role, "content": turn.content} for turn in history],
                user=user,
            )
        )
        return LLMReply(text=result.text, model=result.model, dry_run=result.dry_run)


def get_llm(settings: "Settings") -> LLMProvider:
    """Pick the inference provider. Dry-run unless explicitly enabled live."""

    if not settings.messaging_llm_live:
        return DryRunLLM(model=settings.llm_model or "dry")

    provider = (settings.llm_provider or "anthropic").lower()
    if settings.llm_api_key:
        return BridgeLLM(
            provider=provider,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=getattr(settings, "llm_base_url", ""),
        )
    return DryRunLLM(model=settings.llm_model or "dry")
