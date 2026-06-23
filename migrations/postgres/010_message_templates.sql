-- Phase 10 — message templates / quick replies (Module C productivity).
-- Absorbed from WASender templates + WhatICket QuickMessage. Variables rendered as {{key}}.

create table if not exists message_templates (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  name text not null,
  body text not null,            -- supports {{name}}, {{protocol}}, ... placeholders
  shortcut text,                 -- quick-access key, e.g. "/saudacao"
  created_at timestamptz not null default now()
);
create index if not exists idx_templates_agency on message_templates(agency_id);
