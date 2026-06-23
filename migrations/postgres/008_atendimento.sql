-- Phase 8 (Atendimento) — multi-agent inbox / ticketing on top of the messaging core.
-- Patterns absorbed from WhatICket (Ticket / Queue / QueueOption / QueueIntegration), rewritten as
-- ORIGINAL schema aligned to FGOS conventions: agency_id on every table, uuid PKs, timestamptz,
-- event-driven (rows here are emitted on stream:events and mirrored to BI like the rest of the core).
-- See docs/REVERSE-ENGINEERING-KB.md §8.

-- Departments / queues
create table if not exists queues (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  name text not null,
  color text not null default '#00f0ff',
  greeting_message text not null default '',
  out_of_hours_message text not null default '',
  schedules jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_queues_agency on queues(agency_id);

-- Agents per queue (N:N with app_users)
create table if not exists user_queues (
  agency_id uuid not null,
  user_id uuid not null references app_users(id) on delete cascade,
  queue_id uuid not null references queues(id) on delete cascade,
  primary key (user_id, queue_id)
);

-- Chatbot menu tree (self-referencing)
create table if not exists queue_options (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  queue_id uuid not null references queues(id) on delete cascade,
  parent_id uuid references queue_options(id) on delete cascade,
  title text,
  message text,
  option text,
  created_at timestamptz not null default now()
);
create index if not exists idx_queue_options_queue on queue_options(queue_id, parent_id);

-- Bot delegation to an external orchestrator (n8n / typebot / openai / dialogflow)
create table if not exists queue_integrations (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  queue_id uuid references queues(id) on delete cascade,
  type text not null,                       -- typebot | n8n | openai | dialogflow
  name text not null,
  url_n8n text,                             -- FGOS already runs n8n
  prompt text,                              -- OpenAI
  config jsonb not null default '{}'::jsonb,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

-- Tickets (conversation with a lifecycle)
create table if not exists tickets (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  contact_id uuid not null references contacts(id) on delete cascade,
  session_id uuid references chat_sessions(id) on delete set null,
  queue_id uuid references queues(id) on delete set null,
  assigned_user_id uuid references app_users(id) on delete set null,
  status text not null default 'pending',   -- pending | open | closed
  channel text not null default 'whatsapp',
  unread_count int not null default 0,
  last_message text,
  is_group boolean not null default false,
  chatbot boolean not null default false,
  queue_option_id uuid references queue_options(id) on delete set null,
  rating int,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_tickets_agency_status on tickets(agency_id, status, updated_at desc);
create index if not exists idx_tickets_contact on tickets(contact_id);

-- Ticket lifecycle audit (transitions) — feeds BI like other events
create table if not exists ticket_traking (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  ticket_id uuid not null references tickets(id) on delete cascade,
  user_id uuid references app_users(id) on delete set null,
  action text not null,                     -- created | assigned | queued | opened | reopened | closed | rated
  detail text,
  created_at timestamptz not null default now()
);
create index if not exists idx_ticket_traking_ticket on ticket_traking(ticket_id, created_at);
