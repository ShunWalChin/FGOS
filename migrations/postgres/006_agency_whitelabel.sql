-- Phase 5 — white-label + self-service onboarding.
-- Each agency gets a public slug (subdomain/path), a plan, and a branding blob
-- (display name, colors, logo) so the shell can theme per tenant.

alter table agencies
  add column if not exists slug text,
  add column if not exists plan text not null default 'trial',
  add column if not exists branding jsonb not null default '{}'::jsonb;

create unique index if not exists uq_agencies_slug
  on agencies(slug) where slug is not null;
