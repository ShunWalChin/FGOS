from __future__ import annotations

from dataclasses import dataclass

from core_engine.ai.guardrails import GuardrailDecision


REGIME_LABELS = {
    "manual": "IA apenas sugere; humano executa.",
    "semi": "IA executa ações reversíveis; humano aprova ações sensíveis.",
    "auto": "IA pode executar quando risco e confiança passam nos gates.",
}


@dataclass(frozen=True)
class GovernanceInput:
    action: str
    regime: str = "semi"
    confidence: float = 0.7
    impact: str = "medium"
    reversible: bool = True
    guardrail: GuardrailDecision | None = None


@dataclass(frozen=True)
class GovernanceDecision:
    status: str
    reason: str
    required_approval: bool
    risk_score: int
    regime_description: str


def evaluate_governance(payload: GovernanceInput) -> GovernanceDecision:
    regime = payload.regime if payload.regime in REGIME_LABELS else "semi"
    impact_score = {"low": 10, "medium": 35, "high": 65, "critical": 85}.get(payload.impact, 35)
    confidence_penalty = int(max(0.0, 1.0 - min(1.0, payload.confidence)) * 45)
    irreversible_penalty = 20 if not payload.reversible else 0
    guardrail_score = payload.guardrail.risk_score if payload.guardrail else 0
    risk_score = min(100, impact_score + confidence_penalty + irreversible_penalty + guardrail_score)

    if payload.guardrail and payload.guardrail.action == "block":
        return GovernanceDecision(
            status="blocked",
            reason="Guardrail bloqueou a ação.",
            required_approval=True,
            risk_score=risk_score,
            regime_description=REGIME_LABELS[regime],
        )
    if regime == "manual":
        return GovernanceDecision(
            status="review",
            reason="Regime manual exige aprovação humana.",
            required_approval=True,
            risk_score=risk_score,
            regime_description=REGIME_LABELS[regime],
        )
    if regime == "semi" and (risk_score >= 55 or not payload.reversible):
        return GovernanceDecision(
            status="review",
            reason="Regime semi-autônomo exige revisão para risco alto ou ação irreversível.",
            required_approval=True,
            risk_score=risk_score,
            regime_description=REGIME_LABELS[regime],
        )
    if regime == "auto" and risk_score >= 75:
        return GovernanceDecision(
            status="review",
            reason="Regime automático reteve ação de risco elevado.",
            required_approval=True,
            risk_score=risk_score,
            regime_description=REGIME_LABELS[regime],
        )
    return GovernanceDecision(
        status="approved",
        reason="Gates de governança aprovados.",
        required_approval=False,
        risk_score=risk_score,
        regime_description=REGIME_LABELS[regime],
    )

