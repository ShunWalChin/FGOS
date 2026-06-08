from __future__ import annotations

import asyncio
from unittest import TestCase

from core_engine.messaging.flow import DEFAULT_FLOW, advance
from core_engine.providers.llm import ChatTurn, DryRunLLM, get_llm
from core_engine.settings import Settings


def _settings(**over) -> Settings:
    base = dict(meta_app_secret="x", meta_verify_token="y")
    base.update(over)
    return Settings(**base)


class FlowAdvanceTest(TestCase):
    def test_first_contact_greets_and_stays_at_start(self) -> None:
        d = advance(DEFAULT_FLOW, None, {}, "oi")
        self.assertTrue(d.replies)               # greeted
        self.assertEqual(d.next_node_id, "start")
        self.assertFalse(d.handoff)

    def test_choosing_human_triggers_handoff(self) -> None:
        d = advance(DEFAULT_FLOW, "start", {}, "quero falar com um atendente")
        self.assertTrue(d.handoff)
        self.assertEqual(d.next_node_id, "handoff")

    def test_choosing_info_moves_to_qualify_and_asks(self) -> None:
        d = advance(DEFAULT_FLOW, "start", {}, "quero informações")
        self.assertEqual(d.next_node_id, "qualify")
        self.assertTrue(any("serviço" in r or "servico" in r for r in d.replies))
        self.assertFalse(d.use_ai)

    def test_qualify_captures_answer_into_context(self) -> None:
        d = advance(DEFAULT_FLOW, "qualify", {}, "tráfego pago")
        self.assertEqual(d.context_updates.get("interesse"), "tráfego pago")

    def test_unmatched_falls_back_to_ai(self) -> None:
        d = advance(DEFAULT_FLOW, "start", {}, "blá blá pergunta aleatória")
        self.assertTrue(d.use_ai)
        self.assertEqual(d.next_node_id, "ai")

    def test_ai_node_stays_on_ai(self) -> None:
        d = advance(DEFAULT_FLOW, "ai", {"interesse": "x"}, "e quanto custa?")
        self.assertTrue(d.use_ai)
        self.assertEqual(d.next_node_id, "ai")


class DryRunLLMTest(TestCase):
    def test_dry_run_echoes_and_flags_dry(self) -> None:
        llm = DryRunLLM()
        reply = asyncio.run(llm.complete(system="s", history=[ChatTurn("user", "oi")], user="quero o link"))
        self.assertTrue(reply.dry_run)
        self.assertIn("quero o link", reply.text)

    def test_get_llm_is_dry_when_not_live(self) -> None:
        self.assertIsInstance(get_llm(_settings(messaging_llm_live=False)), DryRunLLM)

    def test_get_llm_falls_back_to_dry_without_key(self) -> None:
        # live requested but no api key -> safe dry-run, never crashes
        self.assertIsInstance(get_llm(_settings(messaging_llm_live=True, llm_api_key="")), DryRunLLM)
