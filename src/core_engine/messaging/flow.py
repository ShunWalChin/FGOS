from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# A flow is a dict of nodes. Node types:
#   ask     — send `say`, then branch on the user's reply (transitions/default)
#   say     — send `say`, then go to `default`
#   ai      — defer the reply to the LLM (use_ai)
#   handoff — switch the session to a human agent
#
# This is the "ManyChat" state machine of docs/ARCHITECTURE.md §4-C kept minimal
# and PURE: no DB, no network — so every branch is unit-testable. The session's
# current_node_id + context live in Postgres (chat_sessions).

DEFAULT_FLOW: dict[str, dict[str, Any]] = {
    "start": {
        "type": "ask",
        "say": (
            "Olá! 👋 Sou o assistente da agência. Posso te dar (1) informações "
            "ou (2) falar com um atendente. O que prefere?"
        ),
        "transitions": [
            {"to": "handoff", "keywords": ["2", "humano", "atendente", "pessoa", "alguem", "alguém"]},
            {"to": "qualify", "keywords": ["1", "info", "informa", "serviço", "servico", "preco", "preço"]},
        ],
        "default": "ai",
    },
    "qualify": {
        "type": "ask",
        "say": "Perfeito! Sobre qual serviço: tráfego pago, social media ou criação de site?",
        "capture": "interesse",
        "transitions": [
            {"to": "handoff", "keywords": ["humano", "atendente", "falar com"]},
        ],
        "default": "ai",
    },
    "ai": {"type": "ai"},
    "handoff": {
        "type": "handoff",
        "say": "Sem problema! Vou te transferir para um de nossos atendentes. 🙌",
    },
}


@dataclass(frozen=True)
class Decision:
    replies: list[str] = field(default_factory=list)  # fixed bot messages to send
    next_node_id: str = "start"
    use_ai: bool = False        # the worker should call the LLM and send its reply
    handoff: bool = False       # switch session.mode -> human
    context_updates: dict[str, Any] = field(default_factory=dict)


def _match_target(node: dict[str, Any], text: str) -> str | None:
    low = text.lower()
    for transition in node.get("transitions", []):
        if any(kw in low for kw in transition["keywords"]):
            return transition["to"]
    return node.get("default")


def _enter(flow: dict[str, dict[str, Any]], node_id: str) -> tuple[list[str], bool, bool]:
    """Immediate effect of arriving at a node: (replies, use_ai, handoff)."""
    node = flow.get(node_id, {})
    node_type = node.get("type")
    if node_type == "handoff":
        return ([node["say"]] if node.get("say") else [], False, True)
    if node_type == "ai":
        return ([], True, False)
    say = node.get("say")
    return ([say] if say else [], False, False)


def advance(
    flow: dict[str, dict[str, Any]],
    current_node_id: str | None,
    context: dict[str, Any] | None,
    user_text: str,
) -> Decision:
    """Drive the bot one turn forward. Pure: returns what to do, changes nothing."""

    ctx = dict(context or {})
    replies: list[str] = []

    # First contact: just greet (enter `start`) and wait. The trigger message is
    # not treated as an answer to a question the user hasn't seen yet.
    if not current_node_id or current_node_id not in flow:
        r, use_ai, handoff = _enter(flow, "start")
        return Decision(r, "start", use_ai, handoff, ctx)

    node = flow[current_node_id]
    node_type = node.get("type")

    if node_type == "ai":
        return Decision([], "ai", True, False, ctx)
    if node_type == "handoff":
        return Decision([node.get("say", "")] if node.get("say") else [], current_node_id, False, True, ctx)

    # ask / say: capture the answer, then branch
    if node.get("capture"):
        ctx[node["capture"]] = user_text

    target = _match_target(node, user_text)
    if not target:
        return Decision(replies, current_node_id, False, False, ctx)

    r, use_ai, handoff = _enter(flow, target)
    replies += r
    return Decision(replies, target, use_ai, handoff, ctx)
