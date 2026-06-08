from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_EVENT_HOPS = 5


class Actor(BaseModel):
    """Who caused an event to exist."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["user", "system", "webhook"]
    id: str = Field(min_length=1)


class EventEnvelope(BaseModel):
    """Canonical event envelope shared by every service and worker."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    event: str
    version: int = Field(default=1, ge=1)
    agency_id: UUID
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor: Actor
    trace_id: UUID = Field(default_factory=uuid4)
    hops: int = Field(default=0, ge=0)
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event")
    @classmethod
    def validate_event_name(cls, value: str) -> str:
        parts = value.split(".")
        if len(parts) != 3 or any(not part for part in parts):
            raise ValueError("event must use namespace.entity.action format")
        if any(part.lower() != part for part in parts):
            raise ValueError("event names must be lowercase")
        return value

    @field_validator("occurred_at")
    @classmethod
    def force_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @property
    def exhausted_hops(self) -> bool:
        return self.hops > MAX_EVENT_HOPS

    def to_stream_payload(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_stream_payload(cls, payload: str | bytes) -> "EventEnvelope":
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        return cls.model_validate_json(payload)

    def child(
        self,
        event: str,
        data: dict[str, Any],
        *,
        actor: Actor | None = None,
        version: int = 1,
    ) -> "EventEnvelope":
        """Create a follow-up event while preserving trace lineage."""

        return EventEnvelope(
            event=event,
            version=version,
            agency_id=self.agency_id,
            actor=actor or Actor(type="system", id="automation"),
            trace_id=self.trace_id,
            hops=self.hops + 1,
            data=data,
        )
