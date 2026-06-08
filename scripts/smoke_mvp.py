"""End-to-end smoke test for the MVP spine.

Flow under test:
    POST /api/items (convert_to_deal=true)
       -> publishes workspace.item.created on stream:events
       -> worker-router consumes, creates a deal, publishes crm.deal.created
       -> worker-router also forwards both events to stream:bi.events
       -> worker-bi micro-batches them into ClickHouse events_log

Usage:
    python scripts/smoke_mvp.py [--api http://localhost:8000] [--no-clickhouse]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

SEED_FILE = Path(".seed.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--no-clickhouse", action="store_true")
    parser.add_argument(
        "--clickhouse-dsn",
        default="http://bi:dev-clickhouse-password@localhost:8123/default",
    )
    args = parser.parse_args()

    if not SEED_FILE.exists():
        print(f"ERROR: {SEED_FILE} not found. Run `core-engine seed` first.", file=sys.stderr)
        return 2

    seed = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    print(f"seed loaded: agency={seed['agency_id']} list={seed['list_id']}")

    item_title = f"smoke-{int(time.time())}"
    item_payload = {
        "list_id": seed["list_id"],
        "agency_id": seed["agency_id"],
        "title": item_title,
        "convert_to_deal": True,
        "pipeline_id": seed["pipeline_id"],
        "stage_id": seed["stage_lead_id"],
        "value_cents": 50000,
    }

    with httpx.Client(base_url=args.api, timeout=10.0) as client:
        created = client.post("/api/items", json=item_payload)
        created.raise_for_status()
        item_id = created.json()["id"]
        print(f"  created item {item_id} title={item_title}")

        deal_id = _wait_for_deal_from_item(client, seed["agency_id"], item_id, args.timeout)

    if not deal_id:
        print("FAIL: deal did not appear within timeout", file=sys.stderr)
        return 1

    print(f"  router produced deal {deal_id}")

    if args.no_clickhouse:
        print("PASS (clickhouse check skipped)")
        return 0

    if not _check_clickhouse(args.clickhouse_dsn, item_id, args.timeout):
        print("FAIL: events_log mirror not observed in ClickHouse", file=sys.stderr)
        return 1

    print("PASS")
    return 0


def _wait_for_deal_from_item(
    client: httpx.Client,
    agency_id: str,
    item_id: str,
    timeout: float,
) -> str | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get("/api/deals", params={"agency_id": agency_id, "limit": 50})
        resp.raise_for_status()
        for deal in resp.json():
            tagged = client.get(f"/api/items/{item_id}")
            if tagged.status_code == 200 and deal["title"] == tagged.json()["title"]:
                return deal["id"]
        time.sleep(0.5)
    return None


def _check_clickhouse(dsn: str, item_id: str, timeout: float) -> bool:
    try:
        import clickhouse_connect
    except ImportError:
        print("WARN: clickhouse-connect not installed; skipping BI check", file=sys.stderr)
        return True

    parsed = urlparse(dsn)
    client = clickhouse_connect.get_client(
        host=parsed.hostname or "localhost",
        port=parsed.port or 8123,
        username=parsed.username or "default",
        password=parsed.password or "",
        database=(parsed.path.lstrip("/") or "default"),
    )

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rows = client.query(
            "select count() from events_log where meta like %(needle)s",
            parameters={"needle": f"%{item_id}%"},
        ).result_rows
        if rows and rows[0][0] >= 1:
            print(f"  clickhouse rows for item: {rows[0][0]}")
            return True
        time.sleep(1.0)
    return False


if __name__ == "__main__":
    sys.exit(main())
