from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx


Message = dict[str, str]


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    provider: str
    dry_run: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    raw: Any = field(default=None, repr=False)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMClient(Protocol):
    provider: str
    model: str

    async def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.4,
        max_tokens: int = 700,
    ) -> LLMResult:
        ...


def _prompt_preview(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user" and message.get("content"):
            return message["content"].strip().splitlines()[0][:160]
    return "sua mensagem"


@dataclass
class DryRunClient:
    model: str = "dry"
    provider: str = "dry"
    canned: str = ""

    async def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.4,
        max_tokens: int = 700,
    ) -> LLMResult:
        text = self.canned or f"(IA dry-run) Recebi: {_prompt_preview(messages)}. Como posso ajudar?"
        return LLMResult(text=text, model=self.model, provider=self.provider, dry_run=True)


class OpenAICompatibleClient:
    """Async OpenAI-compatible chat client.

    Covers OpenAI, Groq, local OpenAI-compatible gateways and several proxy
    providers by changing only ``base_url``.
    """

    def __init__(self, *, provider: str, model: str, api_key: str, base_url: str) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.4,
        max_tokens: int = 700,
    ) -> LLMResult:
        start = time.perf_counter()
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        return LLMResult(
            text=message.get("content") or "",
            model=data.get("model") or self.model,
            provider=self.provider,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=(time.perf_counter() - start) * 1000,
            raw=data,
        )


class AnthropicClient:
    def __init__(self, *, model: str, api_key: str, base_url: str = "https://api.anthropic.com/v1") -> None:
        self.provider = "anthropic"
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.4,
        max_tokens: int = 700,
    ) -> LLMResult:
        start = time.perf_counter()
        system_parts = [m.get("content", "") for m in messages if m.get("role") == "system"]
        turns = [m for m in messages if m.get("role") != "system"]
        payload = {
            "model": self.model,
            "system": "\n\n".join(part for part in system_parts if part),
            "messages": turns,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.post(f"{self.base_url}/messages", headers=headers, json=payload)
            resp.raise_for_status()
        data = resp.json()
        content = data.get("content") or []
        text = "".join(part.get("text", "") for part in content if part.get("type") == "text")
        usage = data.get("usage") or {}
        return LLMResult(
            text=text,
            model=data.get("model") or self.model,
            provider=self.provider,
            prompt_tokens=int(usage.get("input_tokens") or 0),
            completion_tokens=int(usage.get("output_tokens") or 0),
            latency_ms=(time.perf_counter() - start) * 1000,
            raw=data,
        )


def build_messages(*, system: str | None, history: list[Message], user: str) -> list[Message]:
    messages: list[Message] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.extend({"role": m.get("role", "user"), "content": m.get("content", "")} for m in history)
    messages.append({"role": "user", "content": user})
    return messages


def create_client(
    *,
    provider: str,
    model: str,
    api_key: str = "",
    live: bool = False,
    base_url: str = "",
) -> LLMClient:
    provider = (provider or "dry").lower()
    if not live or not api_key:
        return DryRunClient(model=model or "dry")
    if provider == "anthropic":
        return AnthropicClient(model=model, api_key=api_key, base_url=base_url or "https://api.anthropic.com/v1")
    if provider == "openai":
        return OpenAICompatibleClient(
            provider="openai",
            model=model,
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1",
        )
    if provider == "groq":
        return OpenAICompatibleClient(
            provider="groq",
            model=model,
            api_key=api_key,
            base_url=base_url or "https://api.groq.com/openai/v1",
        )
    if provider in {"openai-compatible", "compatible"}:
        return OpenAICompatibleClient(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1",
        )
    return DryRunClient(model=model or "dry", provider="dry")

