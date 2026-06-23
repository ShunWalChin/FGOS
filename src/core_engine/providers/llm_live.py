"""Live LLM adapters — the integration point left open in providers/llm.py.

OpenAI-compatible (OpenAI, Groq, Mistral, OpenRouter, DeepSeek, Together, xAI) share one adapter;
Anthropic and Google have their own. `resolve_agency_provider` reads the agency's default ai_model,
decrypts its key (pgcrypto) and returns a ready provider — or None to fall back to dry-run.
"""

from __future__ import annotations

import httpx
from sqlalchemy import text

from core_engine.providers.llm import ChatTurn, LLMProvider, LLMReply

# OpenAI-compatible /chat/completions bases
OPENAI_COMPAT_BASE: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "together": "https://api.together.xyz/v1",
    "xai": "https://api.x.ai/v1",
}
PROVIDERS = sorted(set(OPENAI_COMPAT_BASE) | {"anthropic", "google"})


class OpenAICompatLLM(LLMProvider):
    def __init__(self, *, api_key: str, model: str, base_url: str) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def complete(self, *, system: str, history: list[ChatTurn], user: str) -> LLMReply:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages += [{"role": t.role, "content": t.content} for t in history]
        messages.append({"role": "user", "content": user})
        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages, "max_tokens": 900},
            )
            resp.raise_for_status()
            data = resp.json()
        return LLMReply(text=data["choices"][0]["message"]["content"], model=self.model)


class AnthropicLLM(LLMProvider):
    def __init__(self, *, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def complete(self, *, system: str, history: list[ChatTurn], user: str) -> LLMReply:
        messages = [{"role": t.role, "content": t.content} for t in history]
        messages.append({"role": "user", "content": user})
        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                json={"model": self.model, "system": system or "", "messages": messages, "max_tokens": 900},
            )
            resp.raise_for_status()
            data = resp.json()
        textout = "".join(b.get("text", "") for b in data.get("content", []))
        return LLMReply(text=textout, model=self.model)


class GoogleLLM(LLMProvider):
    def __init__(self, *, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def complete(self, *, system: str, history: list[ChatTurn], user: str) -> LLMReply:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.model}:generateContent?key={self.api_key}")
        prompt = (system + "\n\n" if system else "") + user
        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.post(url, json={"contents": [{"role": "user", "parts": [{"text": prompt}]}]})
            resp.raise_for_status()
            data = resp.json()
        textout = data["candidates"][0]["content"]["parts"][0]["text"]
        return LLMReply(text=textout, model=self.model)


def make_provider(provider: str, api_key: str, model: str, base_url: str | None = None) -> LLMProvider:
    p = (provider or "").lower()
    if p == "anthropic":
        return AnthropicLLM(api_key=api_key, model=model)
    if p == "google":
        return GoogleLLM(api_key=api_key, model=model)
    base = base_url or OPENAI_COMPAT_BASE.get(p)
    if not base:
        raise ValueError(f"unknown provider: {provider}")
    return OpenAICompatLLM(api_key=api_key, model=model, base_url=base)


async def resolve_agency_provider(session, agency_id: str, encryption_key: str) -> LLMProvider | None:
    """Return the agency's default LLM (decrypted), or None when none is configured."""
    row = (
        await session.execute(
            text(
                """
                select provider, model, base_url,
                       pgp_sym_decrypt(api_key_enc, :key) as api_key
                from ai_models
                where agency_id = :a and is_default = true and api_key_enc is not null
                limit 1
                """
            ),
            {"a": str(agency_id), "key": encryption_key},
        )
    ).mappings().first()
    if not row or not row["api_key"]:
        return None
    return make_provider(row["provider"], row["api_key"], row["model"], row["base_url"])
