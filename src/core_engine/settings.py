from __future__ import annotations

from uuid import UUID

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "core-engine"
    environment: str = "development"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    redis_url: str = "redis://:dev-redis-password@localhost:6379/0"
    database_url: str = "postgresql+asyncpg://core:dev-postgres-password@localhost:5432/saas_core"
    clickhouse_dsn: str = "http://bi:dev-clickhouse-password@clickhouse:8123/default"

    default_agency_id: UUID = Field(
        default=UUID("00000000-0000-0000-0000-000000000001"),
        description="Development fallback until webhook account resolution is wired.",
    )

    meta_app_secret: str = ""
    meta_verify_token: str = ""

    stream_events: str = "stream:events"
    stream_webhooks_meta: str = "stream:webhooks.meta"
    stream_bi: str = "stream:bi.events"

    worker_group: str = "core-engine"
    max_event_hops: int = 5
    messaging_debounce_seconds: int = 2
    social_worker_poll_seconds: float = 1.0
    bi_batch_size: int = 500
    bi_flush_seconds: float = 5.0


def get_settings() -> Settings:
    return Settings()
