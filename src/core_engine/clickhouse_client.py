from __future__ import annotations

from urllib.parse import unquote, urlparse


def create_clickhouse_client(dsn: str):
    """Build a clickhouse-connect client from a DSN like
    http://user:pass@host:8123/database. Shared by the BI worker (writes) and the
    BI read API (CQRS — reads only here, never against Postgres)."""

    import clickhouse_connect

    parsed = urlparse(dsn)
    scheme = parsed.scheme or "http"
    database = parsed.path.lstrip("/") or "default"
    return clickhouse_connect.get_client(
        interface="https" if scheme == "https" else "http",
        host=parsed.hostname or "localhost",
        port=parsed.port or (8443 if scheme == "https" else 8123),
        username=unquote(parsed.username or "default"),
        password=unquote(parsed.password or ""),
        database=database,
        secure=scheme == "https",
    )
