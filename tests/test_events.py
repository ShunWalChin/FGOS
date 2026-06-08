from __future__ import annotations

from datetime import datetime
from unittest import TestCase
from uuid import UUID

from core_engine.events import Actor, EventEnvelope


AGENCY_ID = UUID("00000000-0000-0000-0000-000000000001")


class EventEnvelopeTest(TestCase):
    def test_event_round_trip_and_trace_lineage(self) -> None:
        event = EventEnvelope(
            event="crm.deal.won",
            agency_id=AGENCY_ID,
            actor=Actor(type="user", id="u_1"),
            data={"value_cents": 500000},
        )

        restored = EventEnvelope.from_stream_payload(event.to_stream_payload())
        child = restored.child("messaging.session.notify", {"deal_id": "d_1"})

        self.assertEqual(restored.event_id, event.event_id)
        self.assertEqual(child.trace_id, event.trace_id)
        self.assertEqual(child.hops, 1)
        self.assertEqual(child.agency_id, AGENCY_ID)

    def test_event_name_must_be_lowercase_namespace_entity_action(self) -> None:
        with self.assertRaises(ValueError):
            EventEnvelope(
                event="CRM.deal.won",
                agency_id=AGENCY_ID,
                actor={"type": "system", "id": "test"},
            )

    def test_naive_datetime_is_normalized_to_utc(self) -> None:
        event = EventEnvelope(
            event="crm.deal.won",
            agency_id=AGENCY_ID,
            actor={"type": "system", "id": "test"},
            occurred_at=datetime(2026, 6, 8, 11, 52),
        )

        self.assertIsNotNone(event.occurred_at.tzinfo)
