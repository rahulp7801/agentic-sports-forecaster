"""Probe the pending hosted read path and plan owner migrations safely."""

import os
from pathlib import Path
import sys
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import psycopg

# The migrations-only environment does not install the worker project. Load
# its stdlib-only diagnostic module from this checkout's fixed source root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from sportsbet.diagnostics import emit_failure


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
    stage = 'heads'
    try:
        expected = repository_heads() if heads is None else heads
        if not expected:
            raise ValueError("Repository has no migration head")
        try:
            stage = 'dsn'
            dsn = hosted_read_dsn(value)
            stage = 'connect'
            with psycopg.connect(dsn, connect_timeout=5, prepare_threshold=None) as connection:
                stage = 'schema_read'
                with connection.cursor() as cursor:
                    cursor.execute("SELECT version_num FROM alembic_version")
                    current = {row[0] for row in cursor.fetchall()}
                    stage = 'close'
        except psycopg.errors.UndefinedTable:
            return True
        return current != expected
    except Exception as error:
        emit_failure(error, operation='hosted_preflight', stage=stage)
        raise


def probe(value: str) -> None:
    stage = 'dsn'
    try:
        dsn = hosted_read_dsn(value)
        # No named prepared statement or session mutation: transaction pooling
        # can return the server connection immediately after this single read.
        stage = 'connect'
        with psycopg.connect(dsn, connect_timeout=5, prepare_threshold=None) as connection:
            stage = 'dashboard_read'
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM dashboard_snapshots LIMIT 1")
                stage = 'close'
    except Exception as error:
        emit_failure(error, operation='hosted_preflight', stage=stage)
        raise


def main() -> None:
    stage = 'mode'
    try:
        mode = sys.argv[1] if len(sys.argv) == 2 else "--probe" if len(sys.argv) == 1 else ""
        if mode not in ('--plan-schema', '--require-schema', '--probe'):
            raise ValueError("Invalid preflight mode")
        stage = 'config'
        value = os.environ["DATABASE_URL"]
        if mode == "--plan-schema":
            stage = None  # The API emits its exact failure stage before re-raising.
            needed = migration_needed(value)
            stage = 'output'
            if path := os.environ.get("GITHUB_OUTPUT"):
                with open(path, "a", encoding="utf-8") as output:
                    output.write("migration_needed=" + str(needed).lower() + "\n")
            print("Owner migration required" if needed else "Hosted schema already current")
        elif mode == "--require-schema":
            stage = None
            needed = migration_needed(value)
            stage = 'schema_check'
            if needed:
                raise RuntimeError("Hosted schema is not at the repository head")
            stage = 'output'
            print("Hosted schema is at the repository head")
        elif mode == "--probe":
            stage = None
            probe(value)
            stage = 'output'
            print("Hosted transaction-pool read preflight passed")
    except Exception as error:
        if stage is not None:
            emit_failure(error, operation='hosted_preflight', stage=stage)
        print("Hosted transaction-pool schema/read preflight failed", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
