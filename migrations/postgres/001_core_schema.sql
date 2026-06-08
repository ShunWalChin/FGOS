create extension if not exists pgcrypto;
create extension if not exists citext;

create table if not exists agencies (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  created_at timestamptz not null default now()
);

create table if not exists clients (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null references agencies(id) on delete cascade,
  name text not null,
  created_at timestamptz not null default now()
);

create table if not exists app_users (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null references agencies(id) on delete cascade,
  email citext not null,
  full_name text,
  role text not null default 'member',
  created_at timestamptz not null default now(),
  unique (agency_id, email)
);

create table if not exists workspaces (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null references agencies(id) on delete cascade,
  name text not null,
  created_at timestamptz not null default now()
);

create table if not exists lists (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  parent_id uuid references lists(id) on delete cascade,
  name text not null,
  sort_order double precision not null default 0
);

create table if not exists items (
  id uuid primary key default gen_random_uuid(),
  list_id uuid not null references lists(id) on delete cascade,
  agency_id uuid not null references agencies(id) on delete cascade,
  title text not null,
  status text not null default 'open',
  assignee_id uuid references app_users(id),
  due_at timestamptz,
  fields jsonb not null default '{}'::jsonb,
  sort_order double precision not null default 0,
  version int not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_items_list on items(list_id, status);
create index if not exists idx_items_fields on items using gin (fields jsonb_path_ops);
create index if not exists idx_items_due on items(due_at) where due_at is not null;

create table if not exists social_accounts (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null references agencies(id) on delete cascade,
  client_id uuid references clients(id) on delete set null,
  platform text not null,
  external_account_id text not null,
  access_token_enc bytea not null,
  refresh_token_enc bytea,
  expires_at timestamptz,
  scopes text[] not null default '{}',
  status text not null default 'active',
  updated_at timestamptz not null default now(),
  unique (platform, external_account_id)
);

create table if not exists posts_queue (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null references agencies(id) on delete cascade,
  social_account_id uuid not null references social_accounts(id),
  payload jsonb not null,
  scheduled_at timestamptz not null,
  status text not null default 'pending',
  attempts smallint not null default 0,
  next_attempt_at timestamptz,
  last_error text,
  locked_at timestamptz,
  locked_by text,
  published_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists idx_posts_due on posts_queue(scheduled_at)
  where status = 'pending';
create index if not exists idx_posts_account_status on posts_queue(social_account_id, status);

create table if not exists contacts (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null references agencies(id) on delete cascade,
  full_name text,
  email citext,
  phone text,
  external_ids jsonb not null default '{}'::jsonb,
  tags text[] not null default '{}',
  created_at timestamptz not null default now()
);

create index if not exists idx_contacts_external_ids on contacts using gin (external_ids jsonb_path_ops);
create index if not exists idx_contacts_tags on contacts using gin (tags);

create table if not exists chat_sessions (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null references agencies(id) on delete cascade,
  contact_id uuid not null references contacts(id),
  channel text not null,
  current_node_id text,
  context jsonb not null default '{}'::jsonb,
  mode text not null default 'bot',
  updated_at timestamptz not null default now()
);

create table if not exists messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references chat_sessions(id) on delete cascade,
  direction text not null,
  body text,
  provider_msg_id text,
  created_at timestamptz not null default now()
);

create unique index if not exists uq_messages_provider
  on messages(provider_msg_id) where provider_msg_id is not null;

create table if not exists pipelines (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null references agencies(id) on delete cascade,
  name text not null
);

create table if not exists stages (
  id uuid primary key default gen_random_uuid(),
  pipeline_id uuid not null references pipelines(id) on delete cascade,
  name text not null,
  sort_order double precision not null default 0,
  is_won boolean not null default false,
  is_lost boolean not null default false
);

create table if not exists deals (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null references agencies(id) on delete cascade,
  pipeline_id uuid not null references pipelines(id),
  stage_id uuid not null references stages(id),
  contact_id uuid references contacts(id),
  title text not null,
  value_cents bigint not null default 0,
  currency char(3) not null default 'BRL',
  probability smallint not null default 0,
  sort_order double precision not null default 0,
  version int not null default 1,
  updated_at timestamptz not null default now()
);

create index if not exists idx_deals_stage on deals(stage_id, sort_order);
create index if not exists idx_deals_agency_updated on deals(agency_id, updated_at desc);

create table if not exists processed_events (
  event_id uuid primary key,
  event_type text not null,
  processed_at timestamptz not null default now()
);

create table if not exists event_failures (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null,
  event_type text not null,
  trace_id uuid,
  reason text not null,
  detail text,
  created_at timestamptz not null default now()
);

create index if not exists idx_event_failures_trace on event_failures(trace_id, created_at desc);

create table if not exists worker_heartbeats (
  worker_id text primary key,
  stream text not null,
  last_seen_at timestamptz not null default now(),
  meta jsonb not null default '{}'::jsonb
);

insert into agencies(id, name)
values ('00000000-0000-0000-0000-000000000001', 'Development Agency')
on conflict (id) do nothing;
