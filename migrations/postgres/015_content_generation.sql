-- Phase 15 (Growth gen) — content generation request fields on content_pieces.
-- A piece can be created with status='requested' + a prompt; worker-content generates the draft
-- (dry-run, brand-voice-aware, anti-slop-checked) and flips it to status='draft'.

alter table content_pieces add column if not exists prompt text;
alter table content_pieces add column if not exists model text;

-- claim hot path for the content worker
create index if not exists idx_content_requested on content_pieces(status, created_at)
  where status = 'requested';
