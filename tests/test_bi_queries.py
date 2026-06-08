from __future__ import annotations

from unittest import TestCase

from core_engine import bi_queries

AGENCY = "00000000-0000-0000-0000-000000000001"


class BiQueriesTest(TestCase):
    def test_summary_binds_agency_and_deal_event(self) -> None:
        sql, params = bi_queries.summary_query(AGENCY)
        self.assertIn("from events_log", sql)
        self.assertIn("{agency_id:UUID}", sql)
        self.assertEqual(params["agency_id"], AGENCY)
        self.assertEqual(params["deal_evt"], bi_queries.DEAL_VALUE_EVENT)

    def test_timeseries_clamps_days(self) -> None:
        _, params = bi_queries.timeseries_query(AGENCY, days=9999)
        self.assertEqual(params["days"], 365)
        _, params = bi_queries.timeseries_query(AGENCY, days=0)
        self.assertEqual(params["days"], 1)

    def test_breakdown_clamps_limit_and_orders(self) -> None:
        sql, params = bi_queries.breakdown_query(AGENCY, limit=9999)
        self.assertEqual(params["limit"], 100)
        self.assertIn("order by n desc", sql)

    def test_funnel_filters_crm_events(self) -> None:
        sql, params = bi_queries.funnel_query(AGENCY)
        self.assertIn("like 'crm.%'", sql)
        self.assertEqual(params["agency_id"], AGENCY)

    def test_no_builder_uses_string_interpolation_for_agency(self) -> None:
        # agency_id must be a bound param, never f-stringed into SQL
        for builder in (bi_queries.summary_query, bi_queries.timeseries_query,
                        bi_queries.breakdown_query, bi_queries.funnel_query):
            sql, params = builder(AGENCY)
            self.assertNotIn(AGENCY, sql)
            self.assertEqual(params["agency_id"], AGENCY)
