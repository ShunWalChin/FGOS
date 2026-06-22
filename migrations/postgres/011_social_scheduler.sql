-- Phase 11 (Social scheduler) — content library + repost, absorbed from Stackposts.
-- captions library, media library (folders), and repost fields on the existing posts_queue.

create table if not exists captions (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  title text not null,
  content text not null,
  created_at timestamptz not null default now()
);
create index if not exists idx_captions_agency on captions(agency_id);

create table if not exists media_files (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  parent_id uuid references media_files(id) on delete cascade,   -- folder tree
  is_folder boolean not null default false,
  name text not null,
  url text,
  mime text,
  size_bytes bigint,
  created_at timestamptz not null default now()
);
create index if not exists idx_media_agency_parent on media_files(agency_id, parent_id);

-- repost support on the scheduler (Stackposts repost_frequency/until + reusable caption)
alter table posts_queue add column if not exists repost_frequency int;       -- seconds between reposts
alter table posts_queue add column if not exists repost_until timestamptz;
alter table posts_queue add column if not exists caption_id uuid;
