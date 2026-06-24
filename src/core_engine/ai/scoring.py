from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


SIGNALS = {
    "budget": [
        "orçamento",
        "orcamento",
        "preço",
        "preco",
        "valor",
        "investir",
        "mensalidade",
        "plano",
        "budget",
    ],
    "authority": [
        "sou o dono",
        "sou dono",
        "decisor",
        "diretor",
        "sócio",
        "socio",
        "proprietário",
        "proprietario",
        "aprovar",
    ],
    "need": [
        "preciso",
        "dor",
        "problema",
        "quero melhorar",
        "vender mais",
        "leads",
        "atendimento",
        "automatizar",
    ],
    "timeline": [
        "hoje",
        "essa semana",
        "este mês",
        "este mes",
        "urgente",
        "agora",
        "quando começa",
        "prazo",
    ],
}


@dataclass(frozen=True)
class LeadScore:
    bant_score: int
    probability: int
    temperature: str
    next_best_action: str
    signals: dict[str, bool]
    explanation: list[str]


def _match_any(text: str, phrases: list[str]) -> bool:
    low = text.lower()
    return any(phrase in low for phrase in phrases)


def _has_money(text: str, value_cents: int) -> bool:
    return value_cents > 0 or bool(re.search(r"(r\$|\$)\s?\d+|\d+\s?(mil|k)", text.lower()))


def score_lead(*, title: str = "", notes: str = "", value_cents: int = 0, metadata: dict[str, Any] | None = None) -> LeadScore:
    text = f"{title}\n{notes}\n{metadata or {}}"
    signals = {
        "budget": _has_money(text, value_cents) or _match_any(text, SIGNALS["budget"]),
        "authority": _match_any(text, SIGNALS["authority"]),
        "need": _match_any(text, SIGNALS["need"]),
        "timeline": _match_any(text, SIGNALS["timeline"]),
    }
    bant_score = sum(1 for value in signals.values() if value)
    value_boost = 8 if value_cents >= 500_00 else 0
    probability = min(95, 15 + bant_score * 18 + value_boost)
    temperature = "quente" if bant_score >= 3 else "morno" if bant_score == 2 else "frio"
    if bant_score >= 3:
        next_best_action = "Agendar conversa consultiva e preparar proposta."
    elif signals["need"]:
        next_best_action = "Qualificar orçamento, autoridade e prazo antes da proposta."
    else:
        next_best_action = "Fazer pergunta diagnóstica curta para entender dor e urgência."
    explanation = [
        f"{key}: {'sim' if value else 'não'}" for key, value in signals.items()
    ]
    if value_boost:
        explanation.append("valor estimado reforça prioridade")
    return LeadScore(
        bant_score=bant_score,
        probability=probability,
        temperature=temperature,
        next_best_action=next_best_action,
        signals=signals,
        explanation=explanation,
    )

