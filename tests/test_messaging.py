from __future__ import annotations

from unittest import TestCase

from core_engine.providers.meta import extract_inbound_message


class MetaPayloadTest(TestCase):
    def test_extract_inbound_whatsapp_message(self) -> None:
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "contacts": [{"wa_id": "5511999999999"}],
                                "messages": [
                                    {
                                        "id": "wamid.1",
                                        "from": "5511999999999",
                                        "text": {"body": "quero o link"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }

        inbound = extract_inbound_message(payload)

        self.assertIsNotNone(inbound)
        assert inbound is not None
        self.assertEqual(inbound["text"], "quero o link")
        self.assertIn("5511999999999", inbound["session_id"])
