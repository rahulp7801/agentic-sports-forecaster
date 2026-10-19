"""Fault injection for protected provisioning; no live provider or database calls."""
import importlib.util
from io import BytesIO
import json
import os
from pathlib import Path
import runpy
from types import SimpleNamespace
from urllib.error import URLError
from urllib.parse import urlsplit

import psycopg
import pytest


SPEC = importlib.util.spec_from_file_location(
    "waitlist_provision_diagnostics", Path("ops/provision_waitlist.py")
)
provisioner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provisioner)
PRIVATE = "PRIVATE-DSN-TOKEN-SQL-AND-EXCEPTION-NOTE"
READER = (
    "postgresql://sportsbet_dashboard.projectref:fixture-reader@"
    "aws-0-us-west-1.pooler.supabase.com:5432/postgres?sslmode=verify-full"
)
OWNER = READER.replace("sportsbet_dashboard.projectref:fixture-reader", "postgres.projectref:fixture-owner")
ENV = {
    "GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/master", "GITHUB_SHA": "a" * 40,
    "VERCEL_PROJECT_ID": provisioner.PROJECT, "VERCEL_ORG_ID": provisioner.TEAM,
    "VERCEL_TOKEN": "fixture-token", "DATABASE_URL": READER, "DATABASE_MIGRATION_URL": OWNER,
}


def diagnostic(capsys, stage, error_type, sqlstate=None):
    captured = capsys.readouterr()
    assert captured.out == ""
    assert PRIVATE not in captured.err
    lines = captured.err.splitlines()
    assert len(lines) == 1
    expected = {
        "schema_version": 1, "diagnostic_kind": "operation_failure",
        "operation": "waitlist_provision", "stage": stage, "error_type": error_type,
    }
    if sqlstate is not None:
        expected["sqlstate"] = sqlstate
    assert json.loads(lines[0]) == expected


@pytest.mark.parametrize("stage", ["provider_team", "provider_project", "environment_metadata"])
@pytest.mark.parametrize("kind", [TimeoutError, URLError])
def test_real_provider_transport_failures_identify_operation_without_retry_or_db(
    stage, kind, monkeypatch, capsys
):
    error = kind(PRIVATE)
    error.add_note(PRIVATE)
    calls = []
    paths = ["/v2/teams/", "/v9/projects/", "/v10/projects/"]
    failed_index = ["provider_team", "provider_project", "environment_metadata"].index(stage)

    class Opener:
        def open(self, request, timeout):
            index = len(calls)
            calls.append((request.get_method(), urlsplit(request.full_url).path, timeout))
            if index == failed_index:
                raise error
            response = (
                {"id": provisioner.TEAM, "billing": {"plan": "hobby"}}
                if index == 0 else
                {"id": provisioner.PROJECT, "accountId": provisioner.TEAM, "rootDirectory": "frontend"}
            )
            return BytesIO(json.dumps(response).encode())

    monkeypatch.setattr(provisioner, "build_opener", lambda *_: Opener())

    def unexpected(_):
        pytest.fail("Provider transport failure must precede any database connection")

    with pytest.raises(kind) as stopped:
        provisioner.provision(ENV, connection=unexpected)
    assert stopped.value is error
    assert len(calls) == failed_index + 1
    assert all(method == "GET" and timeout == 15 for method, _, timeout in calls)
    assert all(path.startswith(paths[index]) for index, (_, path, _) in enumerate(calls))
    diagnostic(capsys, stage, kind.__name__)


class SyntheticProvision:
    """Trace actual provision control flow while simulating external effects."""

    def __init__(self, monkeypatch, *, existing=False, fail_at=None, error=None):
        self.existing = existing
        self.fail_at = fail_at
        self.error = error or RuntimeError(PRIVATE)
        self.trace = []
        self.entries_count = 0
        self.permissions_count = 0
        self.values = [self.entry(provisioner.MARKER + "a" * 64)] if existing else []
        self.provider = SimpleNamespace(attest=self.attest, entries=self.entries, create=self.create)
        self.pgconn = SimpleNamespace(encrypt_password=self.encrypt_password)
        monkeypatch.setattr(provisioner, "verify_permissions", self.permissions)
        monkeypatch.setattr(provisioner.secrets, "token_urlsafe", lambda _: "fixture-generated-password")

    @staticmethod
    def entry(marker):
        return {"key": provisioner.KEY, "type": "sensitive", "target": ["production"], "comment": marker}

    def step(self, name):
        self.trace.append(name)
        if name == self.fail_at:
            raise self.error

    def attest(self):
        self.step("provider_attest")

    def entries(self):
        name = ["environment_metadata", "prepublish_metadata", "postpublish_metadata"][self.entries_count]
        self.entries_count += 1
        self.step(name)
        return self.values.copy()

    def create(self, value, marker):
        # An acknowledgement can be lost after a successful external write.
        self.values = [self.entry(marker)]
        self.step("secret_create")

    def connection(self, value):
        assert value == OWNER
        self.step("connect")
        return self

    def __enter__(self):
        return self

    def __exit__(self, error_type, error, traceback):
        self.trace.append("close")
        if error_type is None and self.fail_at == "close":
            raise self.error
        return False

    def execute(self, statement, parameters=None):
        if isinstance(statement, str):
            if statement == "SELECT version_num FROM alembic_version":
                self.step("schema_read")
                return SimpleNamespace(fetchall=lambda: [(provisioner.HEAD,)])
            if statement == "SELECT 1 FROM pg_roles WHERE rolname=%s":
                assert parameters == (provisioner.ROLE,)
                self.step("role_read")
                return SimpleNamespace(fetchone=lambda: (1,) if self.existing else None)
            assert statement in (
                "GRANT USAGE ON SCHEMA private_access TO sportsbet_waitlist_writer",
                "GRANT EXECUTE ON FUNCTION private_access.join_waitlist(text) TO sportsbet_waitlist_writer",
            )
            self.step("grant_usage" if statement.startswith("GRANT USAGE") else "grant_execute")
        else:
            text = str(statement)
            assert "CREATE ROLE" in text or "COMMENT ON ROLE" in text
            self.step("role_create" if "CREATE ROLE" in text else "role_comment")

    def encrypt_password(self, password, role, algorithm):
        assert password == b"fixture-generated-password"
        assert role == provisioner.ROLE.encode() and algorithm == b"scram-sha-256"
        self.step("password_verifier")
        return b"SCRAM-SHA-256$fixture-verifier"

    def permissions(self, connection, marker):
        assert connection is self and marker.startswith(provisioner.MARKER)
        name = "existing_permissions" if self.existing else (
            "new_permissions" if self.permissions_count == 0 else "postpublish_permissions"
        )
        self.permissions_count += 1
        self.step(name)

    def commit(self):
        self.step("commit")

    def login(self, value):
        assert urlsplit(value).username == provisioner.ROLE + ".projectref"
        self.step("login")

    def run(self):
        return provisioner.provision(ENV, self.provider, self.connection, self.login)


EXISTING_TRACE = [
    "provider_attest", "environment_metadata", "connect", "schema_read", "role_read",
    "existing_permissions", "close",
]
NEW_TRACE = [
    "provider_attest", "environment_metadata", "connect", "schema_read", "role_read",
    "password_verifier", "role_create", "role_comment", "grant_usage", "grant_execute",
    "new_permissions", "commit", "login", "prepublish_metadata", "secret_create",
    "postpublish_metadata", "postpublish_permissions", "close",
]


@pytest.mark.parametrize("existing", [True, False])
def test_successful_paths_retain_external_call_order_and_are_quiet(existing, monkeypatch, capsys):
    fixture = SyntheticProvision(monkeypatch, existing=existing)
    result = fixture.run()
    assert fixture.trace == (EXISTING_TRACE if existing else NEW_TRACE)
    assert result.startswith("Existing managed" if existing else "New dedicated")
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize("existing,stage", [
    (True, "connect"), (True, "schema_read"), (True, "role_read"),
    (True, "existing_permissions"), (True, "close"),
    (False, "commit"), (False, "login"), (False, "prepublish_metadata"),
    (False, "secret_create"), (False, "postpublish_metadata"),
    (False, "postpublish_permissions"), (False, "close"),
])
def test_failure_keeps_exception_identity_stops_at_boundary_and_redacts(
    existing, stage, monkeypatch, capsys
):
    error = RuntimeError(PRIVATE)
    error.add_note(PRIVATE)
    error.__cause__ = psycopg.errors.QueryCanceled(PRIVATE)
    fixture = SyntheticProvision(monkeypatch, existing=existing, fail_at=stage, error=error)
    with pytest.raises(RuntimeError) as stopped:
        fixture.run()
    assert stopped.value is error
    expected = EXISTING_TRACE if existing else NEW_TRACE
    prefix = expected[:expected.index(stage) + 1]
    # A failed connection has no context to close; body failures close once.
    if stage not in ("connect", "close"):
        prefix += ["close"]
    assert fixture.trace == prefix
    assert fixture.trace.count(stage) == 1
    if existing or NEW_TRACE.index(stage) < NEW_TRACE.index("secret_create"):
        assert "secret_create" not in fixture.trace
    else:
        assert fixture.trace.count("secret_create") == 1
    diagnostic(capsys, stage, "RuntimeError", "57014")


def test_connection_failure_does_not_change_existing_timeout_contract(monkeypatch):
    error = psycopg.OperationalError(PRIVATE)
    calls = []

    def connect(value, **kwargs):
        calls.append((value, kwargs))
        raise error

    monkeypatch.setattr(provisioner.psycopg, "connect", connect)
    with pytest.raises(psycopg.OperationalError) as stopped:
        provisioner.connect(OWNER)
    assert stopped.value is error
    assert calls == [(OWNER, {"connect_timeout": 5, "prepare_threshold": None,
                             "options": "-c statement_timeout=5000 -c lock_timeout=3000"})]


def test_cli_emits_one_transport_diagnostic_and_redacted_failure(monkeypatch, capsys):
    error = URLError(PRIVATE)
    error.add_note(PRIVATE)
    calls = []

    class Opener:
        def open(self, request, timeout):
            calls.append(request.get_method())
            raise error

    monkeypatch.setattr(os, "environ", ENV)
    monkeypatch.setattr("sys.argv", ["ops/provision_waitlist.py"])
    monkeypatch.setattr("urllib.request.build_opener", lambda *_: Opener())
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path("ops/provision_waitlist.py", run_name="__main__")
    assert stopped.value.code == 1 and calls == ["GET"]
    captured = capsys.readouterr()
    assert captured.out == "" and PRIVATE not in captured.err
    lines = captured.err.splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {
        "schema_version": 1, "diagnostic_kind": "operation_failure",
        "operation": "waitlist_provision", "stage": "provider_team", "error_type": "URLError",
    }
    assert lines[1].startswith("Private waitlist provisioning failed;")
