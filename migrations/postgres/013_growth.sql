-- Phase 13 (Growth/Conteúdo) — brand voice + content pieces, absorbed from fat-tech-growthOS.
-- Brand voice = tone/avoid/anti-slop/autonomy config; content pieces = generated drafts with a
-- review lifecycle. JSONB used for arrays to keep asyncpg binding simple.

create table if not exists brand_voices (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  name text not null,
  tagline text,
  tone jsonb not null default '[]'::jsonb,         -- ["professional","approachable"]
  avoid jsonb not null default '[]'::jsonb,         -- words/phrases to avoid
  personality text,
  industry text,
  platforms jsonb not null default '{}'::jsonb,     -- per-platform config
  anti_slop jsonb not null default '{}'::jsonb,     -- {banned_phrases:[], style_rules:[]}
  autonomy text not null default 'semi',            -- manual | semi | auto
  created_at timestamptz not null default now()
);
create index if not exists idx_brand_voices_agency on brand_voices(agency_id);

create table if not exists content_pieces (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  brand_voice_id uuid references brand_voices(id) on delete set null,
  type text not null,                  -- carousel | copy | video_brief | sales_page | seo
  platform text,                       -- instagram | linkedin | ...
  title text not null,
  body text,
  status text not null default 'draft',    -- draft | approved | published
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_content_agency_status on content_pieces(agency_id, status, updated_at desc);
