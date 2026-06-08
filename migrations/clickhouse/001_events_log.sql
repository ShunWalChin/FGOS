create table if not exists events_log
(
  occurred_at DateTime64(3),
  agency_id UUID,
  event_type LowCardinality(String),
  entity_id String,
  value_cents Int64,
  meta String
)
engine = MergeTree
partition by toYYYYMM(occurred_at)
order by (agency_id, event_type, occurred_at);
