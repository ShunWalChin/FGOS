-- Phase: auth. Give app_users a password hash so they can log in to the web/mobile
-- app. Tokens carry agency_id (tenant) + user id + role.

alter table app_users
  add column if not exists password_hash text;

create index if not exists idx_app_users_email on app_users(email);

-- The dev login (dev@fgos.local / fgosdev) is created by `fgos seed` with a real
-- PBKDF2 hash computed in Python — never hardcode a hash in SQL.
