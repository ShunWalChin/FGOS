-- Lets every consumer-role have its own idempotency receipt for the same event_id.
-- Without this, a router forwarding an event to stream:bi.events would cause the
-- BI worker to skip it as "already processed", losing every analytical insert.

alter table processed_events
  drop constraint if exists processed_events_pkey;

alter table processed_events
  add column if not exists worker_role text not null default 'default';

alter table processed_events
  add constraint processed_events_pkey primary key (event_id, worker_role);
