from __future__ import annotations

from typing import Any

# Pure builders for the BI read API. Each returns (sql, params) for ClickHouse's
# {name:Type} parameter binding — no I/O, so they are fully unit-testable and the
# read path stays strictly on ClickHouse (CQRS, docs/ARCHITECTURE.md §7).

DEAL_VALUE_EVENT = "crm.deal.created"


def summary_query(agency_id: str) -> tuple[str, dict[str, Any]]:
    sql = """
        select
          count()                                                as total_events,
          uniqExact(event_type)                                  as event_types,
          sumIf(value_cents, event_type = {deal_evt:String})     as deal_value_cents,
          countIf(event_type = 'social.post.published')          as posts_published,
          countIf(event_type = 'messaging.message.inbound')      as msgs_in,
          countIf(event_type = 'messaging.message.outbound')     as msgs_out
        from events_log
        where agency_id = {agency_id:UUID}
    """
    return sql, {"agency_id": agency_id, "deal_evt": DEAL_VALUE_EVENT}


def timeseries_query(agency_id: str, days: int = 30) -> tuple[str, dict[str, Any]]:
    days = max(1, min(int(days), 365))
    sql = """
        select toDate(occurred_at) as day, count() as events
        from events_log
        where agency_id = {agency_id:UUID}
          and occurred_at >= now() - toIntervalDay({days:UInt32})
        group by day
        order by day
    """
    return sql, {"agency_id": agency_id, "days": days}


def breakdown_query(agency_id: str, limit: int = 20) -> tuple[str, dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    sql = """
        select event_type, count() as n
        from events_log
        where agency_id = {agency_id:UUID}
        group by event_type
        order by n desc
        limit {limit:UInt32}
    """
    return sql, {"agency_id": agency_id, "limit": limit}


def funnel_query(agency_id: str) -> tuple[str, dict[str, Any]]:
    sql = """
        select event_type, count() as n
        from events_log
        where agency_id = {agency_id:UUID}
          and event_type like 'crm.%'
        group by event_type
        order by n desc
    """
    return sql, {"agency_id": agency_id}
