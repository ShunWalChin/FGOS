-- Phase 9 (Campanhas) — bulk messaging with contact lists and per-recipient shipping.
-- Absorbed from WhatICket (Campaign/CampaignShipping/ContactList) + WASender (templates/jobs),
-- rewritten ORIGINAL on the FGOS event bus. Dry-run by default (MESSAGING_LIVE=false).
-- See docs/REVERSE-ENGINEERING-KB.md §7 and ATENDIMENTO-INTEGRATION-REPORT.md §5.

create table if not exists contact_lists (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  name text not null,
  created_at timestamptz not null default now()
);
create index if not exists idx_contact_lists_agency on contact_lists(agency_id);

create table if not exists contact_list_items (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  contact_list_id uuid not null references contact_lists(id) on delete cascade,
  name text not null default '',
  number text not null,             -- phone / external id
  email text,
  is_valid boolean not null default true,
  created_at timestamptz not null default now()
);
create index if not exists idx_cli_list on contact_list_items(contact_list_id);

create table if not exists campaigns (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  name text not null,
  contact_list_id uuid references contact_lists(id) on delete set null,
  messages jsonb not null default '[]'::jsonb,   -- rotation pool (anti-ban): message variations
  status text not null default 'draft',          -- draft | scheduled | running | cancelled | done
  scheduled_at timestamptz,
  completed_at timestamptz,
  interval_seconds int not null default 5,       -- pacing between sends
  created_at timestamptz not null default now()
);
create index if not exists idx_campaigns_agency_status on campaigns(agency_id, status);
create index if not exists idx_campaigns_due on campaigns(status, scheduled_at);

create table if not exists campaign_shipping (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  campaign_id uuid not null references campaigns(id) on delete cascade,
  contact_item_id uuid references contact_list_items(id) on delete set null,
  number text not null,
  message text not null,            -- rendered + rotated message for this recipient
  status text not null default 'pending',   -- pending | sent | failed
  delivered_at timestamptz,
  error text,
  created_at timestamptz not null default now()
);
create index if not exists idx_shipping_campaign_status on campaign_shipping(campaign_id, status);
