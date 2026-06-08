from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest import TestCase
from uuid import UUID, uuid4

from core_engine.events import Actor, EventEnvelope
from core_engine.settings import Settings
from core_engine.workers.router import handle

AGENCY_ID = UUID("00000000-0000-0000-0000-000000000001")
PIPELINE_ID = uuid4()
STAGE_ID = uuid4()


@dataclass
class _FakeResult:
    rows: list[tuple]

    def scalar_one(self) -> Any:
        return self.rows[0][0]

    def mappings(self) -> "_FakeResult":
        return self

    def first(self) -> dict[str, Any] | None:
        return None if not self.rows else dict(zip(self._cols, self.rows[0]))

    _cols: tuple[str, ...] = ()


@dataclass
class _FakeSession:
    deal_inserts: list[dict] = field(default_factory=list)
    pipeline_id: UUID = PIPELINE_ID
    stage_id: UUID = STAGE_ID

    async def execute(self, statement, params=None):
        sql = str(statement).strip().lower()
        if sql.startswith("insert into deals"):
            self.deal_inserts.append(params)
            return _FakeResult(rows=[(uuid4(),)])
        if sql.startswith("select p.id"):
            r = _FakeResult(rows=[(self.pipeline_id, self.stage_id)])
            r._cols = ("pipeline_id", "stage_id")
            return r
        return _FakeResult(rows=[])


@dataclass
class _FakeBus:
    published: list[tuple[str, EventEnvelope]] = field(default_factory=list)

    async def publish(self, stream: str, event: EventEnvelope) -> str:
        self.published.append((stream, event))
        return "fake-id"


def _settings() -> Settings:
    return Settings(
        meta_app_secret="x",
        meta_verify_token="y",
    )


def _item_event(*, convert_to_deal: bool, hops: int = 0) -> EventEnvelope:
    return EventEnvelope(
        event="workspace.item.created",
        agency_id=AGENCY_ID,
        actor=Actor(type="user", id="api"),
        hops=hops,
        data={
            "item_id": str(uuid4()),
            "title": "smoke item",
            "convert_to_deal": convert_to_deal,
            "pipeline_id": str(PIPELINE_ID),
            "stage_id": str(STAGE_ID),
            "value_cents": 50000,
        },
    )


class RouterHandlerTest(TestCase):
    def test_item_with_convert_to_deal_creates_deal_and_mirrors_to_bi(self) -> None:
        event = _item_event(convert_to_deal=True)
        session, bus, settings = _FakeSession(), _FakeBus(), _settings()

        asyncio.run(handle(event, session, bus, settings))

        streams = [s for s, _ in bus.published]
        self.assertIn(settings.stream_events, streams)
        self.assertIn(settings.stream_bi, streams)
        self.assertEqual(len(session.deal_inserts), 1)

        child_events = [
            ev for s, ev in bus.published
            if s == settings.stream_events and ev.event == "crm.deal.created"
        ]
        self.assertEqual(len(child_events), 1)
        self.assertEqual(child_events[0].trace_id, event.trace_id)
        self.assertEqual(child_events[0].hops, event.hops + 1)
        self.assertEqual(child_events[0].agency_id, event.agency_id)

    def test_item_without_convert_to_deal_only_mirrors(self) -> None:
        event = _item_event(convert_to_deal=False)
        session, bus, settings = _FakeSession(), _FakeBus(), _settings()

        asyncio.run(handle(event, session, bus, settings))

        self.assertEqual(session.deal_inserts, [])
        self.assertEqual(len(bus.published), 1)
        stream, mirrored = bus.published[0]
        self.assertEqual(stream, settings.stream_bi)
        self.assertEqual(mirrored.event_id, event.event_id)

    def test_unrelated_event_is_still_mirrored_to_bi(self) -> None:
        event = EventEnvelope(
            event="crm.deal.won",
            agency_id=AGENCY_ID,
            actor=Actor(type="user", id="api"),
            data={"deal_id": str(uuid4()), "value_cents": 100000},
        )
        session, bus, settings = _FakeSession(), _FakeBus(), _settings()

        asyncio.run(handle(event, session, bus, settings))

        self.assertEqual(session.deal_inserts, [])
        self.assertEqual([s for s, _ in bus.published], [settings.stream_bi])
