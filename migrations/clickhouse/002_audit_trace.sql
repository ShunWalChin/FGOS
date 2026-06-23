-- Phase 16 (Auditoria) — carry trace lineage into BI so the trace viewer can reconstruct chains.
-- ALTER ADD COLUMN is metadata-only in ClickHouse (instant). Old rows default to empty/0.

alter table events_log add column if not exists trace_id String default '';
alter table events_log add column if not exists hops UInt8 default 0;
alter table events_log add column if not exists event_id String default '';
