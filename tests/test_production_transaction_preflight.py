"""The deployment probe must preserve TLS and only redirect Supabase poolers."""

import importlib.util
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / ".github/scripts/production-transaction-preflight.py"
SPEC = importlib.util.spec_from_file_location("production_transaction_preflight", MODULE)
assert SPEC and SPEC.loader
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def test_supabase_session_url_uses_transaction_port():
    value = (
        "postgresql+psycopg://reader.project:synthetic@"
        "aws-0-us-west-2.pooler.supabase.com:5432/postgres"
        "?sslmode=verify-full&sslrootcert=certs/supabase-prod-ca-2021.crt"
    )
    output = preflight.hosted_read_dsn(value)
    assert "pooler.supabase.com:6543/postgres" in output
    assert "sslmode=verify-full&sslrootcert=" in output


def test_other_hosts_and_ports_are_unchanged():
    value = "postgresql://reader:synthetic@db.example:5432/postgres?sslmode=verify-full"
    assert preflight.hosted_read_dsn(value) == value
    value = value.replace("db.example:5432", "aws-0-us-west-2.pooler.supabase.com:6543")
    assert preflight.hosted_read_dsn(value) == value


@pytest.mark.parametrize(
    "query",
    ["", "sslmode=disable", "sslmode=verify-full&sslmode=disable"],
)
def test_weak_or_ambiguous_tls_fails(query):
    value = "postgresql://reader:synthetic@pooler.example/postgres?" + query
    with pytest.raises(ValueError, match="sslmode=verify-full"):
        preflight.hosted_read_dsn(value)


def test_probe_runs_one_unprepared_read(monkeypatch):
    events = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, sql):
            events.append(sql)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def cursor(self):
            return Cursor()

    def connect(dsn, **kwargs):
        events.append((dsn, kwargs))
        return Connection()

    monkeypatch.setattr(preflight.psycopg, "connect", connect)
    preflight.probe(
        "postgresql://reader:synthetic@aws-0-us-west-2.pooler.supabase.com:5432/"
        "postgres?sslmode=verify-full"
    )
    assert events == [
        (
            "postgresql://reader:synthetic@aws-0-us-west-2.pooler.supabase.com:6543/"
            "postgres?sslmode=verify-full",
            {"connect_timeout": 5, "prepare_threshold": None},
        ),
        "SELECT 1 FROM dashboard_snapshots LIMIT 1",
    ]