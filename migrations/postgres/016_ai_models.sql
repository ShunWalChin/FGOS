-- Phase 17 (IA) — per-agency LLM connections. API keys encrypted at rest with pgcrypto
-- (same pattern as social_accounts.access_token_enc). One default model per agency.

create table if not exists ai_models (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  provider text not null,            -- openai|anthropic|google|groq|mistral|openrouter|deepseek|together|xai
  label text not null,
  model text not null,               -- e.g. gpt-4o, claude-sonnet-4-5, gemini-1.5-pro
  api_key_enc bytea,                 -- pgcrypto pgp_sym_encrypt
  base_url text,                     -- optional override (custom/self-hosted OpenAI-compat)
  is_default boolean not null default false,
  status text not null default 'unverified',   -- unverified | active | error
  last_error text,
  created_at timestamptz not null default now()
);
create index if not exists idx_ai_models_agency on ai_models(agency_id);
-- at most one default per agency
create unique index if not exists uq_ai_models_default on ai_models(agency_id) where is_default;
