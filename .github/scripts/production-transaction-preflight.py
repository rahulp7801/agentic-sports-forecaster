"""Probe the pending hosted read path and plan owner migrations safely."""

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


def repository_heads() -> set[str]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    return set(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())


def migration_needed(value: str, heads: set[str] | None = None) -> bool:
    expected = repository_heads() if heads is None else heads
    if not expected:
        raise ValueError("Repository has no migration head")
    try:
        with psycopg.connect(hosted_read_dsn(value), connect_timeout=5, prepare_threshold=None) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version_num FROM alembic_version")
                current = {row[0] for row in cursor.fetchall()}
    except psycopg.errors.UndefinedTable:
        return True
    return current != expected


def probe(value: str) -> None:
    dsn = hosted_read_dsn(value)
    # No named prepared statement or session mutation: transaction pooling
    # can return the server connection immediately after this single read.
    with psycopg.connect(dsn, connect_timeout=5, prepare_threshold=None) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM dashboard_snapshots LIMIT 1")


if __name__ == "__main__":
    try:
        mode = sys.argv[1] if len(sys.argv) == 2 else "--probe" if len(sys.argv) == 1 else ""
        value = os.environ["DATABASE_URL"]
        if mode == "--plan-schema":
            needed = migration_needed(value)
            if path := os.environ.get("GITHUB_OUTPUT"):
                with open(path, "a", encoding="utf-8") as output:
                    output.write("migration_needed=" + str(needed).lower() + "\n")
            print("Owner migration required" if needed else "Hosted schema already current")
        elif mode == "--require-schema":
            if migration_needed(value):
                raise RuntimeError("Hosted schema is not at the repository head")
            print("Hosted schema is at the repository head")
        elif mode == "--probe":
            probe(value)
            print("Hosted transaction-pool read preflight passed")
        else:
            raise ValueError("Invalid preflight mode")
    except Exception:
        print("Hosted transaction-pool schema/read preflight failed", file=sys.stderr)
        raise SystemExit(1)