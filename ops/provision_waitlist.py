"""Create the waitlist's dedicated credential only inside the protected release gate.

Provider credentials and database URLs stay in memory. Existing roles/passwords
are never changed. Ambiguous publication is left for operator reconciliation.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import psycopg
from psycopg import sql

PROJECT = "prj_xUgCA0BZejb4GZgeOHuJVQqs6M1M"
TEAM = "team_IWsRUaGJj5J56jLXwFs3Wzy7"
ROLE = "sportsbet_waitlist_writer"
KEY = "WAITLIST_DATABASE_URL"
MARKER = "sportsbet-waitlist-writer-v1:"
HEAD = "0048_nba_participation_versions"


class ProvisionError(RuntimeError):
    """Messages must never contain provider response bodies or credentials."""


def fail(message: str):
    raise ProvisionError(message)


def protected_context(env: dict[str, str]) -> None:
    if (env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REF") != "refs/heads/master"
            or not re.fullmatch(r"[a-f0-9]{40}", env.get("GITHUB_SHA", ""))
            or env.get("VERCEL_PROJECT_ID") != PROJECT or env.get("VERCEL_ORG_ID") != TEAM):
        fail("Protected master production context required")
    if any(not env.get(key) for key in ("VERCEL_TOKEN", "DATABASE_URL", "DATABASE_MIGRATION_URL")):
        fail("Protected production credentials missing")


def parsed_dsn(value: str):
    parts = urlsplit(value.replace("postgresql+psycopg://", "postgresql://", 1))
    options = parse_qsl(parts.query, keep_blank_values=True)
    if (parts.scheme != "postgresql" or not parts.hostname or not parts.username or not parts.password
            or parts.fragment or not parts.path.strip("/")
            or [v for k, v in options if k == "sslmode"] != ["verify-full"]
            or any(k not in ("sslmode", "sslrootcert") for k, _ in options)
            or len({k for k, _ in options}) != len(options)):
        fail("Database URL must use verified TLS and unambiguous connection settings")
    # Validate the port before interpolating anything; ValueError is redacted by CLI.
    if parts.port not in (None, 5432, 6543):
        fail("Unsupported production database port")
    return parts


def writer_url(reader: str, owner: str, password: str) -> str:
    read, admin = parsed_dsn(reader), parsed_dsn(owner)
    reader_user, owner_user = unquote(read.username), unquote(admin.username)
    pooled = read.hostname.endswith(".pooler.supabase.com")
    expected = r"sportsbet_dashboard\.([a-z0-9]+)" if pooled else r"sportsbet_dashboard"
    identity = re.fullmatch(expected, reader_user)
    if (not identity or read.hostname != admin.hostname or read.path != admin.path
            or (pooled and owner_user != "postgres." + identity[1])):
        fail("Owner and dashboard connection identities do not match")
    user = ROLE + ("." + identity[1] if pooled else "")
    port = 6543 if pooled else (read.port or 5432)
    host = read.hostname
    if ":" in host:
        host = "[" + host + "]"
    return urlunsplit(read._replace(netloc=f"{quote(user, safe='')}:"
                                  f"{quote(password, safe='')}@{host}:{port}"))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        fail("Provider redirect refused")


class Vercel:
    def __init__(self, token: str):
        self.token = token
        self.opener = build_opener(NoRedirect())

    def request(self, path: str, data=None):
        request = Request("https://api.vercel.com" + path,
                          data=None if data is None else json.dumps(data).encode(),
                          headers={"Authorization": "Bearer " + self.token,
                                   "Content-Type": "application/json"},
                          method="GET" if data is None else "POST")
        try:
            with self.opener.open(request, timeout=15) as response:
                body = response.read(2_000_001)
                if len(body) > 2_000_000:
                    fail("Provider response exceeds limit")
                return json.loads(body)
        except HTTPError as error:
            # Use only fixed operation names and a bounded status. Provider
            # URLs, reasons, headers and bodies can contain credentials.
            operation = {
                ("GET", f"/v2/teams/{TEAM}"): "team attestation",
                ("GET", f"/v9/projects/{PROJECT}?teamId={TEAM}"): "project attestation",
                ("GET", f"/v10/projects/{PROJECT}/env?teamId={TEAM}&decrypt=false"): "environment metadata",
                ("POST", f"/v10/projects/{PROJECT}/env?teamId={TEAM}"): "environment creation",
            }.get((request.get_method(), path), "API")
            status = error.code if type(error.code) is int and 100 <= error.code <= 599 else "unknown"
            raise ProvisionError(
                f"Provider {operation} request rejected (HTTP {status}); response body withheld"
            ) from None

    def attest(self):
        team = self.request("/v2/teams/" + TEAM)
        project = self.request("/v9/projects/" + PROJECT + "?teamId=" + TEAM)
        if (team.get("id") != TEAM or team.get("billing", {}).get("plan") != "hobby"
                or project.get("id") != PROJECT or project.get("accountId") != TEAM
                or project.get("rootDirectory") != "frontend"):
            fail("Pinned Hobby project identity mismatch")

    def entries(self):
        data = self.request(f"/v10/projects/{PROJECT}/env?teamId={TEAM}&decrypt=false")
        if not isinstance(data.get("envs"), list):
            fail("Invalid environment metadata")
        entries = [entry for entry in data["envs"] if entry.get("key") == KEY]
        # A key in preview/custom/branch environments must not be repurposed either.
        if len(entries) > 1:
            fail("Ambiguous waitlist environment settings")
        return entries

    def create(self, value: str, marker: str):
        # Create only: no upsert, PATCH, DELETE, credential read, or overwrite path.
        result = self.request(f"/v10/projects/{PROJECT}/env?" + urlencode({"teamId": TEAM}),
                              {"key": KEY, "value": value, "type": "sensitive",
                               "target": ["production"], "comment": marker})
        if result.get("failed"):
            fail("Waitlist secret publication did not complete")


def managed_entry(entry) -> str:
    comment = entry.get("comment", "")
    if (entry.get("key") != KEY or entry.get("type") != "sensitive"
            or entry.get("target") != ["production"] or entry.get("gitBranch")
            or entry.get("customEnvironmentIds")
            or not re.fullmatch(re.escape(MARKER) + r"[a-f0-9]{64}", comment)):
        fail("Existing waitlist setting is not a managed production secret")
    return comment


def role_marker(conn):
    row = conn.execute("SELECT shobj_description(oid, 'pg_authid') FROM pg_roles WHERE rolname=%s",
                       (ROLE,)).fetchone()
    return None if row is None else row[0]


def expected_function_body() -> str:
    # Read the reviewed literal without importing or executing migration code.
    tree = ast.parse((Path(__file__).resolve().parent.parent /
                     "alembic/versions/0046_private_waitlist.py").read_text(encoding="utf-8"))
    statements = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
                  and isinstance(node.value, str) and node.value.startswith("CREATE FUNCTION private_access.join_waitlist(")]
    if len(statements) != 1:
        fail("Reviewed waitlist function specification missing")
    return statements[0].split("AS $function$", 1)[1].rsplit("$function$", 1)[0].strip()


def verify_permissions(conn, marker: str):
    row = conn.execute("""SELECT rolcanlogin, rolinherit, rolsuper, rolcreatedb,
        rolcreaterole, rolreplication, rolbypassrls FROM pg_roles WHERE rolname=%s""", (ROLE,)).fetchone()
    if row != (True, False, False, False, False, False, False) or role_marker(conn) != marker:
        fail("Dedicated waitlist role attributes or provenance mismatch")
    if conn.execute("""SELECT 1 FROM pg_auth_members m JOIN pg_roles r
        ON r.oid IN (m.member,m.roleid) WHERE r.rolname=%s AND NOT
        (m.roleid=r.oid AND m.member=(SELECT oid FROM pg_roles WHERE rolname=current_user)
         AND m.admin_option AND NOT m.inherit_option AND NOT m.set_option) LIMIT 1""", (ROLE,)).fetchone():
        fail("Waitlist role must have no effective role memberships")
    if conn.execute("""SELECT 1 FROM pg_database WHERE datdba=(SELECT oid FROM pg_roles WHERE rolname=%s)
        OR has_database_privilege(%s,oid,'CREATE') LIMIT 1""", (ROLE, ROLE)).fetchone():
        fail("Waitlist role must not own or create databases")
    if conn.execute("""SELECT 1 FROM pg_namespace WHERE nspname NOT LIKE 'pg_%%'
        AND nspname <> 'information_schema' AND (nspowner=(SELECT oid FROM pg_roles WHERE rolname=%s)
        OR has_schema_privilege(%s,oid,'CREATE')) LIMIT 1""", (ROLE, ROLE)).fetchone():
        fail("Waitlist role must not own or create schemas")
    if conn.execute("""SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname NOT LIKE 'pg_%%' AND n.nspname <> 'information_schema'
        AND c.relkind IN ('r','p','v','m','f','S') AND
        (c.relowner=(SELECT oid FROM pg_roles WHERE rolname=%s) OR
         CASE WHEN c.relkind='S' THEN has_sequence_privilege(%s,c.oid,'USAGE,SELECT,UPDATE')
         ELSE has_table_privilege(%s,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
              OR has_any_column_privilege(%s,c.oid,'SELECT,INSERT,UPDATE,REFERENCES') END)
        LIMIT 1""", (ROLE, ROLE, ROLE, ROLE)).fetchone():
        fail("Waitlist role can access application tables or sequences")
    function = conn.execute("""SELECT p.prosecdef,p.proconfig,p.prorettype='boolean'::regtype,
        has_function_privilege(%s,p.oid,'EXECUTE'),has_schema_privilege(%s,n.oid,'USAGE'),
        p.proowner <> (SELECT oid FROM pg_roles WHERE rolname=%s),p.prosrc
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE p.oid=to_regprocedure('private_access.join_waitlist(text)')""", (ROLE, ROLE, ROLE)).fetchone()
    if (not function or function[:-1] != (True, ["search_path=pg_catalog"], True, True, True, True)
            or function[-1].strip() != expected_function_body()):
        fail("Bounded waitlist write function is missing or changed")
    if conn.execute("""SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname NOT LIKE 'pg_%%' AND n.nspname <> 'information_schema'
        AND p.oid <> 'private_access.join_waitlist(text)'::regprocedure
        AND (p.proowner=(SELECT oid FROM pg_roles WHERE rolname=%s) OR
             (p.prosecdef AND has_schema_privilege(%s,n.oid,'USAGE')
              AND has_function_privilege(%s,p.oid,'EXECUTE'))) LIMIT 1""", (ROLE, ROLE, ROLE)).fetchone():
        fail("Waitlist role owns routines or can execute another privileged function")


def connect(value: str):
    return psycopg.connect(value.replace("postgresql+psycopg://", "postgresql://", 1),
                           connect_timeout=5, prepare_threshold=None,
                           options="-c statement_timeout=5000 -c lock_timeout=3000")


def verify_login(value: str):
    with connect(value) as conn:
        if conn.execute("SELECT current_user").fetchone() != (ROLE,):
            fail("Waitlist credential resolved to the wrong database role")
        # Test the actual password/function but roll back the signup AND counters.
        row = conn.execute("SELECT private_access.join_waitlist(%s)",
                           ("release-" + secrets.token_hex(12) + "@example.invalid",)).fetchone()
        if row not in ((True,), (False,)):
            fail("Waitlist function returned an invalid result")
        conn.rollback()


def provision(env: dict[str, str], provider=None, connection=connect, login=verify_login):
    protected_context(env)
    password = secrets.token_urlsafe(48)
    value = writer_url(env["DATABASE_URL"], env["DATABASE_MIGRATION_URL"], password)
    provider = provider or Vercel(env["VERCEL_TOKEN"])
    provider.attest()
    entries = provider.entries()
    with connection(env["DATABASE_MIGRATION_URL"]) as conn:
        if conn.execute("SELECT version_num FROM alembic_version").fetchall() != [(HEAD,)]:
            fail("Reviewed waitlist migration head required")
        existing = conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (ROLE,)).fetchone()
        if entries:
            marker = managed_entry(entries[0])
            if not existing:
                fail("Stored waitlist credential has no database role; operator reconciliation required")
            verify_permissions(conn, marker)
            return "Existing managed waitlist role privileges verified; no credential changed"
        if existing:
            fail("Waitlist role exists without its managed secret; refusing rotation or repurposing")
        marker = MARKER + hashlib.sha256(value.encode()).hexdigest()
        # Encrypt on the client so plaintext passwords cannot enter SQL logs.
        verifier = conn.pgconn.encrypt_password(password.encode(), ROLE.encode(), b"scram-sha-256").decode()
        conn.execute(sql.SQL("CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB "
                             "NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}").format(
                                 sql.Identifier(ROLE), sql.Literal(verifier)))
        conn.execute(sql.SQL("COMMENT ON ROLE {} IS {}").format(sql.Identifier(ROLE), sql.Literal(marker)))
        conn.execute("GRANT USAGE ON SCHEMA private_access TO sportsbet_waitlist_writer")
        conn.execute("GRANT EXECUTE ON FUNCTION private_access.join_waitlist(text) TO sportsbet_waitlist_writer")
        verify_permissions(conn, marker)
        conn.commit()
        # From this point an interruption can leave a narrowly privileged orphan
        # role. A later run refuses to rotate it or overwrite an existing setting.
        login(value)
        if provider.entries():
            fail("Waitlist setting appeared during provisioning; refusing overwrite")
        provider.create(value, marker)
        stored = provider.entries()
        if len(stored) != 1 or managed_entry(stored[0]) != marker:
            fail("Stored waitlist secret metadata could not be verified; operator reconciliation required")
        verify_permissions(conn, marker)
        return "New dedicated waitlist credential login verified and stored as a production sensitive secret"


if __name__ == "__main__":
    try:
        if len(sys.argv) != 1:
            fail("No command arguments accepted")
        print(provision(dict(os.environ)))
    except ProvisionError as error:
        print("Private waitlist provisioning stopped: " + str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        # Database and provider exceptions can embed passwords or URLs. Do not
        # print exception strings, tracebacks, response bodies or command args.
        print("Private waitlist provisioning failed; inspect protected settings and role provenance. "
              "Existing credentials were not overwritten or rotated. A new unpublished role may require reconciliation.", file=sys.stderr)
        sys.exit(1)
