-- Phase 16 (AI tools) — modular intelligence layer inspired by the SantanderAI study.
-- The implementation stays FGOS-native: tenant scoped, event-friendly, deterministic by default,
-- and separated from the hot Redis Streams ingestion path.

alter table deals add column if not exists bant_score smallint not null default 0;
alter table deals add column if not exists temperature text not null default 'frio';
alter table deals add column if not exists next_best_action text;
alter table deals add column if not exists ai_score jsonb not null default '{}'::jsonb;

create index if not exists idx_deals_ai_priority
  on deals(agency_id, temperature, bant_score desc, updated_at desc);

create table if not exists ai_guardrail_policies (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null references agencies(id) on delete cascade,
  name text not null,
  rules jsonb not null default '{}'::jsonb,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (agency_id, name)
);
create index if not exists idx_ai_guardrail_policies_agency
  on ai_guardrail_policies(agency_id, active, updated_at desc);

create table if not exists ai_guardrail_evaluations (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null references agencies(id) on delete cascade,
  policy_id uuid references ai_guardrail_policies(id) on delete set null,
  surface text not null default 'general',
  action text not null,
  allowed boolean not null,
  risk_score int not null,
  findings jsonb not null default '[]'::jsonb,
  input_excerpt text,
  output_excerpt text,
  created_at timestamptz not null default now()
);
create index if not exists idx_ai_guardrail_eval_agency
  on ai_guardrail_evaluations(agency_id, created_at desc);

create table if not exists knowledge_bases (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null references agencies(id) on delete cascade,
  name text not null,
  description text,
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (agency_id, name)
);
create index if not exists idx_knowledge_bases_agency on knowledge_bases(agency_id, status);

create table if not exists knowledge_documents (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null references agencies(id) on delete cascade,
  knowledge_base_id uuid not null references knowledge_bases(id) on delete cascade,
  title text not null,
  source text,
  body text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_knowledge_documents_base on knowledge_documents(knowledge_base_id, created_at desc);

create table if not exists knowledge_chunks (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null references agencies(id) on delete cascade,
  knowledge_base_id uuid not null references knowledge_bases(id) on delete cascade,
  document_id uuid not null references knowledge_documents(id) on delete cascade,
  chunk_index int not null,
  title text not null,
  body text not null,
  tokens text[] not null default '{}',
  created_at timestamptz not null default now(),
  unique (document_id, chunk_index)
);
create index if not exists idx_knowledge_chunks_base on knowledge_chunks(knowledge_base_id);
create index if not exists idx_knowledge_chunks_tokens on knowledge_chunks using gin(tokens);

create table if not exists ai_governance_audits (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null references agencies(id) on delete cascade,
  action text not null,
  regime text not null,
  status text not null,
  risk_score int not null,
  required_approval boolean not null,
  reason text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_ai_governance_agency
  on ai_governance_audits(agency_id, created_at desc);

create table if not exists lead_score_history (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null references agencies(id) on delete cascade,
  deal_id uuid references deals(id) on delete cascade,
  bant_score smallint not null,
  probability smallint not null,
  temperature text not null,
  next_best_action text not null,
  signals jsonb not null default '{}'::jsonb,
  explanation jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_lead_score_history_deal
  on lead_score_history(deal_id, created_at desc);

create table if not exists ai_vault_notes (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null references agencies(id) on delete cascade,
  kind text not null default 'note',
  title text not null,
  body text not null,
  tags text[] not null default '{}',
  created_by uuid references app_users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_ai_vault_notes_agency
  on ai_vault_notes(agency_id, kind, updated_at desc);
create index if not exists idx_ai_vault_notes_tags
  on ai_vault_notes using gin(tags);

