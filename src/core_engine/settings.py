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

    # Symmetric key used by pgcrypto (pgp_sym_encrypt/decrypt) to keep OAuth
    # tokens encrypted at rest. Rotate via re-encryption; never log it.
    token_encryption_key: str = "dev-token-encryption-key-change-me"

    # Social / OAuth (Module B). Per-platform client credentials are optional in
    # dev: with SOCIAL_LIVE=false the providers run in dry-run (no network calls).
    social_live: bool = False
    oauth_redirect_base: str = "http://localhost:8000"
    meta_client_id: str = ""
    meta_client_secret: str = ""
    tiktok_client_id: str = ""
    tiktok_client_secret: str = ""
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    youtube_client_id: str = ""
    youtube_client_secret: str = ""

    # Messaging / IA (Module C). Dry-run by default: no LLM calls, no outbound
    # network — the whole conversation pipeline runs offline.
    messaging_live: bool = False        # send real outbound messages (Meta Send API)
    messaging_llm_live: bool = False    # call a real LLM provider
    llm_provider: str = "anthropic"     # anthropic | openai | groq
    llm_model: str = "claude-sonnet-4-5"
    llm_api_key: str = ""

    stream_events: str = "stream:events"
    stream_webhooks_meta: str = "stream:webhooks.meta"
    stream_bi: str = "stream:bi.events"

    worker_group: str = "core-engine"
    max_event_hops: int = 5
    messaging_debounce_seconds: int = 2
    social_worker_poll_seconds: float = 1.0
    social_max_attempts: int = 5
    social_rate_limit_cooldown_seconds: int = 900  # pause an account 15min on 429
    bi_batch_size: int = 500
    bi_flush_seconds: float = 5.0


def get_settings() -> Settings:
    return Settings()
