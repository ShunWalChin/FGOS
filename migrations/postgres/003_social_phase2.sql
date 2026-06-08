-- Phase 2 (Social/Ads) — per-account rate-limit pause and external post id.
--
-- The architecture (docs/ARCHITECTURE.md §6) says the rate limit is PER token/account:
-- one client hammered into 429 must not freeze the other 29. We pause only that
-- account via rate_limited_until and the claim query skips it.

alter table social_accounts
  add column if not exists rate_limited_until timestamptz;

-- platform's own id for the published post (idempotent re-publish guard + BI join)
alter table posts_queue
  add column if not exists platform_post_id text;

-- claim hot path: pending + due posts, ordered; partial index keeps it tiny
create index if not exists idx_posts_pending_due
  on posts_queue(scheduled_at)
  where status = 'pending';

-- find an account's live state quickly when claiming / guarding
create index if not exists idx_social_accounts_status
  on social_accounts(agency_id, status);
