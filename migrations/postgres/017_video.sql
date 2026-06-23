-- Phase 18 (Vídeo) — video projects, absorbed from OpenCut (companion web editor).
-- FGOS owns the project (linked to a content piece); the actual editing happens in OpenCut, opened
-- via editor_url (self-hosted OpenCut or opencut.app). No heavy editor embedded in the SPA.

create table if not exists video_projects (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  name text not null,
  content_piece_id uuid references content_pieces(id) on delete set null,
  editor_url text,                       -- OpenCut editor URL (self-hosted or opencut.app)
  status text not null default 'draft',  -- draft | editing | rendered
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_video_projects_agency on video_projects(agency_id);
create index if not exists idx_video_projects_content on video_projects(content_piece_id);
