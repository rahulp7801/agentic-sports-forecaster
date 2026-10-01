"""Probe the pending hosted read path before spending a production deployment."""

import os
import sys
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import psycopg


def hosted_read_dsn(value: str) -> str:
    if value.startswith("postgresql+psycopg://"):
        value = "postgresql://" + value.split("://", 1)[1]
    parts = urlsplit(value)
    if parts.scheme != "postgresql" or not parts.hostname:
        raise ValueError("Invalid hosted database URL")
    modes = [item for key, item in parse_qsl(parts.query, keep_blank_values=True) if key == "sslmode"]
    if modes != ["verify-full"]:
        raise ValueError("Hosted database requires exactly one sslmode=verify-full")
    if parts.hostname.endswith(".pooler.supabase.com") and parts.port == 5432:
        parts = parts._replace(netloc=parts.netloc.rsplit(":", 1)[0] + ":6543")
    return urlunsplit(parts)


def probe(value: str) -> None:
    dsn = hosted_read_dsn(value)
    # No named prepared statement or session mutation: transaction pooling
    # can return the server connection immediately after this single read.
    with psycopg.connect(dsn, connect_timeout=5, prepare_threshold=None) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM dashboard_snapshots LIMIT 1")


if __name__ == "__main__":
    try:
        probe(os.environ["DATABASE_URL"])
    except Exception:
        print("Hosted transaction-pool read preflight failed", file=sys.stderr)
        raise SystemExit(1)
    print("Hosted transaction-pool read preflight passed")