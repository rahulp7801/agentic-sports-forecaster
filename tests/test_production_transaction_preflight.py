"""The deployment probe must preserve TLS and only redirect Supabase poolers."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import parse_qs, urlsplit

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
    parsed = urlsplit(output)
    assert parsed.hostname == "aws-0-us-west-2.pooler.supabase.com"
    assert parsed.port == 6543
    assert parsed.path == "/postgres"
    assert parse_qs(parsed.query) == {
        "sslmode": ["verify-full"],
        "sslrootcert": ["certs/supabase-prod-ca-2021.crt"],
    }


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

def test_schema_plan_skips_owner_only_at_exact_repository_heads(monkeypatch):
    versions = ["head-a"]
    statements = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, sql):
            statements.append(sql)

        def fetchall(self):
            return [(version,) for version in versions]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def cursor(self):
            return Cursor()

    def connect(dsn, **kwargs):
        parsed = urlsplit(dsn)
        assert parsed.hostname == "aws-0-us-west-2.pooler.supabase.com"
        assert parsed.port == 6543
        assert kwargs == {"connect_timeout": 5, "prepare_threshold": None}
        return Connection()

    monkeypatch.setattr(preflight.psycopg, "connect", connect)
    value = (
        "postgresql://reader:synthetic@aws-0-us-west-2.pooler.supabase.com:5432/"
        "postgres?sslmode=verify-full"
    )
    assert preflight.migration_needed(value, {"head-a"}) is False
    assert preflight.migration_needed(value, {"head-b"}) is True
    assert statements == ["SELECT version_num FROM alembic_version"] * 2


def test_missing_version_table_requires_owner_migration(monkeypatch):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, _sql):
            raise preflight.psycopg.errors.UndefinedTable("missing version table")

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def cursor(self):
            return Cursor()

    monkeypatch.setattr(preflight.psycopg, "connect", lambda *_args, **_kwargs: Connection())
    assert preflight.migration_needed(
        "postgresql://reader:synthetic@db.example/postgres?sslmode=verify-full",
        {"head-a"},
    ) is True


def test_schema_plan_requires_a_repository_head():
    with pytest.raises(ValueError, match="no migration head"):
        preflight.migration_needed(
            "postgresql://reader:synthetic@db.example/postgres?sslmode=verify-full",
            set(),
        )
    assert preflight.repository_heads()


LOCAL_DSN = 'postgresql://reader:synthetic@localhost:6543/postgres?sslmode=verify-full'


def mocked_database(monkeypatch, *, fault=None, error=None, versions=('head-a',)):
    """All paths use invented inputs and a mocked connector, never a live DB."""
    events = []
    def stop(stage):
        if fault == stage:
            raise error
    class Cursor:
        def __enter__(self):
            stop('cursor_enter')
            return self
        def __exit__(self, *_):
            stop('cursor_close')
            return False
        def execute(self, sql):
            events.append(('query', sql))
            stop('execute')
        def fetchall(self):
            stop('fetchall')
            return [(version,) for version in versions]
    class Connection:
        def __enter__(self):
            stop('connection_enter')
            return self
        def __exit__(self, *_):
            stop('close')
            return False
        def cursor(self):
            return Cursor()
    def connect(dsn, **kwargs):
        events.append(('connect', dsn, kwargs))
        stop('connect')
        return Connection()
    monkeypatch.setattr(preflight.psycopg, 'connect', connect)
    monkeypatch.setattr(preflight, 'repository_heads', lambda: {'head-a'})
    return events


@pytest.mark.parametrize('api,fault,stage', [
    ('schema', 'heads', 'heads'), ('schema', 'dsn', 'dsn'),
    ('schema', 'connect', 'connect'), ('schema', 'connection_enter', 'connect'),
    ('schema', 'cursor_enter', 'schema_read'), ('schema', 'execute', 'schema_read'),
    ('schema', 'fetchall', 'schema_read'), ('schema', 'cursor_close', 'close'),
    ('schema', 'close', 'close'), ('probe', 'dsn', 'dsn'),
    ('probe', 'connect', 'connect'), ('probe', 'execute', 'dashboard_read'),
    ('probe', 'cursor_close', 'close'), ('probe', 'close', 'close'),
])
def test_api_failure_reports_exact_stage_once_and_reraises_same_error(monkeypatch,capsys,api,fault,stage):
    error = preflight.psycopg.errors.ConnectionFailure('private SQL DSN provider body')
    error.add_note('private note')
    events = mocked_database(monkeypatch, fault=fault, error=error)
    def fail(*_):
        raise error
    if fault == 'heads':
        monkeypatch.setattr(preflight, 'repository_heads', fail)
    if fault == 'dsn':
        monkeypatch.setattr(preflight, 'hosted_read_dsn', fail)
    with pytest.raises(preflight.psycopg.errors.ConnectionFailure) as raised:
        (preflight.migration_needed if api == 'schema' else preflight.probe)(LOCAL_DSN)
    assert raised.value is error and error.__notes__ == ['private note']
    output = capsys.readouterr()
    assert output.out == ''
    assert json.loads(output.err) == {'schema_version': 1, 'diagnostic_kind': 'operation_failure',
        'operation': 'hosted_preflight', 'stage': stage, 'error_type': 'ConnectionFailure', 'sqlstate': '08006'}
    assert all(secret not in output.err for secret in ('private', 'SELECT', 'localhost', 'Traceback'))
    connects = [event for event in events if event[0] == 'connect']
    assert len(connects) == (0 if fault in ('heads', 'dsn') else 1)
    if connects:
        assert connects[0] == ('connect', LOCAL_DSN, {'connect_timeout': 5, 'prepare_threshold': None})
    assert sum(event[0] == 'query' for event in events) <= 1


def test_missing_schema_table_remains_migration_required_without_failure_record(monkeypatch,capsys):
    error = preflight.psycopg.errors.UndefinedTable('private table detail')
    events = mocked_database(monkeypatch, fault='execute', error=error)
    assert preflight.migration_needed(LOCAL_DSN) is True
    assert capsys.readouterr().err == ''
    assert events == [('connect', LOCAL_DSN, {'connect_timeout': 5, 'prepare_threshold': None}),
                      ('query', 'SELECT version_num FROM alembic_version')]


@pytest.mark.parametrize('fault,stage,error_type', [
    ('mode', 'mode', 'ValueError'), ('config', 'config', 'KeyError'),
    ('heads', 'heads', 'ValueError'), ('dsn', 'dsn', 'ValueError'),
    ('connect', 'connect', 'ConnectionFailure'), ('close', 'close', 'ConnectionFailure'),
    ('schema_check', 'schema_check', 'RuntimeError'), ('output', 'output', 'OSError'),
])
def test_cli_failure_is_one_redacted_stage_and_existing_failed_exit(
        monkeypatch,tmp_path,capsys,fault,stage,error_type):
    error = preflight.psycopg.errors.ConnectionFailure('private connection detail')
    events = mocked_database(monkeypatch, fault=fault, error=error,
        versions=('head-b',) if fault == 'schema_check' else ('head-a',))
    monkeypatch.setenv('DATABASE_URL', LOCAL_DSN)
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    mode = '--require-schema' if fault == 'schema_check' else '--plan-schema'
    monkeypatch.setattr(sys, 'argv', [str(MODULE), '--private-invalid' if fault == 'mode' else mode])
    if fault == 'config':
        monkeypatch.delenv('DATABASE_URL')
    elif fault == 'heads':
        monkeypatch.setattr(preflight, 'repository_heads', lambda: set())
    elif fault == 'dsn':
        monkeypatch.setenv('DATABASE_URL', 'postgresql://private:private@localhost/db?sslmode=disable')
    elif fault == 'output':
        monkeypatch.setenv('GITHUB_OUTPUT', str(tmp_path))  # Existing directory cannot be appended as a file.
    with pytest.raises(SystemExit) as raised:
        preflight.main()
    assert raised.value.code == 1
    output = capsys.readouterr()
    assert output.out == ''
    lines = output.err.splitlines()
    assert len(lines) == 2 and lines[1] == 'Hosted transaction-pool schema/read preflight failed'
    record = json.loads(lines[0])
    assert record['operation'] == 'hosted_preflight' and record['stage'] == stage
    if fault == 'output':
        assert record['error_type'] in ('IsADirectoryError', 'PermissionError')
    else:
        assert record['error_type'] == error_type
    assert record.get('sqlstate') == ('08006' if fault in ('connect', 'close') else None)
    assert all(secret not in output.err for secret in ('private', 'SELECT', 'localhost', 'Traceback'))
    assert sum(event[0] == 'connect' for event in events) <= 1


@pytest.mark.parametrize('mode,versions,message,planned', [
    ('--plan-schema', ('head-a',), 'Hosted schema already current', 'false'),
    ('--plan-schema', ('head-b',), 'Owner migration required', 'true'),
    ('--require-schema', ('head-a',), 'Hosted schema is at the repository head', None),
    ('--probe', ('head-a',), 'Hosted transaction-pool read preflight passed', None),
    (None, ('head-a',), 'Hosted transaction-pool read preflight passed', None),
])
def test_cli_success_strings_schema_output_and_single_reads_remain_exact(
        monkeypatch,tmp_path,capsys,mode,versions,message,planned):
    events = mocked_database(monkeypatch, versions=versions)
    monkeypatch.setenv('DATABASE_URL', LOCAL_DSN)
    destination = tmp_path / 'outputs.txt'
    monkeypatch.setenv('GITHUB_OUTPUT', str(destination))
    monkeypatch.setattr(sys, 'argv', [str(MODULE)] + ([] if mode is None else [mode]))
    preflight.main()
    output = capsys.readouterr()
    assert output.out == message + '\n' and output.err == ''
    if planned is None:
        assert not destination.exists()
    else:
        assert destination.read_text() == 'migration_needed=' + planned + '\n'
    query = 'SELECT 1 FROM dashboard_snapshots LIMIT 1' if mode in (None, '--probe') else 'SELECT version_num FROM alembic_version'
    assert events == [('connect', LOCAL_DSN, {'connect_timeout': 5, 'prepare_threshold': None}), ('query', query)]


def test_direct_script_imports_only_confined_stdlib_diagnostics_without_installed_project(tmp_path):
    # -I -S removes cwd/PYTHONPATH/site-packages. Only this fake psycopg is supplied;
    # a migrations-only caller must not need worker/project dependencies installed.
    program = r'''
import importlib.util, runpy, sys, types
assert importlib.util.find_spec('sportsbet') is None
psycopg = types.ModuleType('psycopg')
class ConnectionFailure(Exception):
    sqlstate = '08006'
class UndefinedTable(Exception):
    pass
def connect(dsn, **kwargs):
    assert dsn == 'postgresql://reader:synthetic@localhost:6543/postgres?sslmode=verify-full'
    assert kwargs == {'connect_timeout': 5, 'prepare_threshold': None}
    raise ConnectionFailure('private credential and provider text')
psycopg.connect = connect
psycopg.errors = types.SimpleNamespace(UndefinedTable=UndefinedTable)
sys.modules['psycopg'] = psycopg
sys.argv = [sys.argv[1], '--probe']
runpy.run_path(sys.argv[0], run_name='__main__')
'''
    environment = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR') if key in os.environ}
    environment['DATABASE_URL'] = LOCAL_DSN
    result = subprocess.run([sys.executable, '-I', '-S', '-c', program, str(MODULE)],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=20)
    assert result.returncode == 1 and result.stdout == ''
    lines = result.stderr.splitlines()
    assert len(lines) == 2 and lines[1] == 'Hosted transaction-pool schema/read preflight failed'
    assert json.loads(lines[0]) == {'schema_version': 1, 'diagnostic_kind': 'operation_failure',
        'operation': 'hosted_preflight', 'stage': 'connect', 'error_type': 'ConnectionFailure', 'sqlstate': '08006'}
    assert 'private' not in result.stderr and 'Traceback' not in result.stderr
