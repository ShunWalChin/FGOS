-- Phase 12 (Voz) — voice agents, absorbed from fat-tech-voz-panel (ElevenLabs Convai).
-- A voice agent is a per-agency conversational voice front-end (Convai agent_id).

create table if not exists voice_agents (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  name text not null,
  provider text not null default 'elevenlabs',   -- elevenlabs | (future: vapi, retell)
  agent_id text not null,                          -- ElevenLabs Convai agent id
  status text not null default 'active',           -- active | paused
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_voice_agents_agency on voice_agents(agency_id);
