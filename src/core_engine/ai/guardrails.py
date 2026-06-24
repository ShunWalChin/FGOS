from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


DEFAULT_BLOCKED_PHRASES = [
    "ignore previous instructions",
    "ignore as instruções anteriores",
    "developer message",
    "system prompt",
    "jailbreak",
    "bypass policy",
    "exfiltrate",
]

DEFAULT_SENSITIVE_PATTERNS = {
    "cpf": r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b",
    "card": r"\b(?:\d[ -]*?){13,19}\b",
    "secret": r"\b(?:api[_-]?key|token|senha|password|secret)\s*[:=]\s*\S+",
}


@dataclass(frozen=True)
class GuardrailPolicy:
    name: str = "default"
    blocked_phrases: list[str] = field(default_factory=lambda: list(DEFAULT_BLOCKED_PHRASES))
    sensitive_patterns: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SENSITIVE_PATTERNS))
    require_handoff_phrases: list[str] = field(
        default_factory=lambda: ["processo judicial", "chargeback", "cancelar contrato", "reclamação formal"]
    )
    max_response_chars: int = 1600
    strict: bool = False

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "GuardrailPolicy":
        payload = payload or {}
        return cls(
            name=str(payload.get("name") or "default"),
            blocked_phrases=[str(x) for x in payload.get("blocked_phrases", DEFAULT_BLOCKED_PHRASES)],
            sensitive_patterns={
                str(k): str(v) for k, v in payload.get("sensitive_patterns", DEFAULT_SENSITIVE_PATTERNS).items()
            },
            require_handoff_phrases=[str(x) for x in payload.get("require_handoff_phrases", [])]
            or ["processo judicial", "chargeback", "cancelar contrato", "reclamação formal"],
            max_response_chars=int(payload.get("max_response_chars") or 1600),
            strict=bool(payload.get("strict", False)),
        )


@dataclass(frozen=True)
class GuardrailFinding:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    action: str
    risk_score: int
    findings: list[GuardrailFinding]


def _contains(text: str, phrase: str) -> bool:
    return phrase.lower() in text.lower()


def evaluate_guardrails(*, user_text: str, assistant_text: str = "", policy: GuardrailPolicy | None = None) -> GuardrailDecision:
    policy = policy or GuardrailPolicy()
    combined = f"{user_text}\n{assistant_text}".strip()
    findings: list[GuardrailFinding] = []

    for phrase in policy.blocked_phrases:
        if phrase and _contains(combined, phrase):
            findings.append(
                GuardrailFinding(
                    code="prompt_injection",
                    severity="high",
                    message=f"Encontrado padrão bloqueado: {phrase}",
                )
            )

    for name, pattern in policy.sensitive_patterns.items():
        if pattern and re.search(pattern, assistant_text or combined, flags=re.IGNORECASE):
            findings.append(
                GuardrailFinding(
                    code=f"sensitive_{name}",
                    severity="high" if name in {"card", "secret"} else "medium",
                    message=f"Possível dado sensível detectado: {name}",
                )
            )

    for phrase in policy.require_handoff_phrases:
        if phrase and _contains(user_text, phrase):
            findings.append(
                GuardrailFinding(
                    code="handoff_recommended",
                    severity="medium",
                    message=f"Assunto pede revisão humana: {phrase}",
                )
            )

    if assistant_text and len(assistant_text) > policy.max_response_chars:
        findings.append(
            GuardrailFinding(
                code="too_long",
                severity="low",
                message="Resposta maior que o limite da política.",
            )
        )

    risk_score = min(
        100,
        sum({"low": 10, "medium": 30, "high": 60}.get(item.severity, 20) for item in findings),
    )
    high = any(item.severity == "high" for item in findings)
    medium = any(item.severity == "medium" for item in findings)
    if high or (policy.strict and findings):
        action = "block"
    elif medium:
        action = "handoff"
    elif findings:
        action = "revise"
    else:
        action = "allow"
    return GuardrailDecision(
        allowed=action in {"allow", "revise"},
        action=action,
        risk_score=risk_score,
        findings=findings,
    )

