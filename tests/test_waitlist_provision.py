"""The protected provisioner uses only disposable SQL and simulated provider calls."""
import importlib.util
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, unquote
import uuid

import psycopg
from psycopg import sql
import pytest

spec=importlib.util.spec_from_file_location("waitlist_provision",Path("ops/provision_waitlist.py"))
provisioner=importlib.util.module_from_spec(spec);spec.loader.exec_module(provisioner)
READER="postgresql://sportsbet_dashboard.projectref:fixture-reader@aws-0-us-west-1.pooler.supabase.com:5432/postgres?sslmode=verify-full"
OWNER=READER.replace("sportsbet_dashboard.projectref:fixture-reader","postgres.projectref:fixture-owner")
ENV={"GITHUB_ACTIONS":"true","GITHUB_REF":"refs/heads/master","GITHUB_SHA":"a"*40,
     "VERCEL_PROJECT_ID":provisioner.PROJECT,"VERCEL_ORG_ID":provisioner.TEAM,
     "VERCEL_TOKEN":"fixture-token","DATABASE_URL":READER,"DATABASE_MIGRATION_URL":OWNER}


def test_provisioner_requires_the_exact_reviewed_repository_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    assert ScriptDirectory.from_config(Config('alembic.ini')).get_heads()==[provisioner.HEAD]

class Provider:
    def __init__(self):self.values=[];self.calls=[];self.mode="success";self.value=None
    def attest(self):self.calls.append("attest")
    def entries(self):self.calls.append("entries");return self.values.copy()
    def create(self,value,marker):
        self.calls.append("create");self.value=value
        if self.mode=="failed":raise RuntimeError("simulated provider failure")
        self.values=[{"key":provisioner.KEY,"type":"sensitive","target":["production"],"comment":marker}]
        if self.mode=="ambiguous":raise RuntimeError("simulated lost acknowledgement")

@pytest.mark.parametrize("changes",[
    {"GITHUB_ACTIONS":"false"},{"GITHUB_REF":"refs/heads/other"},{"GITHUB_SHA":"bad"},
    {"VERCEL_PROJECT_ID":"foreign"},{"VERCEL_ORG_ID":"foreign"},{"VERCEL_TOKEN":""},
    {"DATABASE_MIGRATION_URL":""},{"DATABASE_URL":""},
])
def test_context_rejects_before_connection_or_provider(changes):
    def unexpected(*args):pytest.fail("unsafe external call")
    with pytest.raises(provisioner.ProvisionError):provisioner.provision(ENV|changes,provider=unexpected,connection=unexpected)

@pytest.mark.parametrize("reader",[
    READER.replace("verify-full","require"),READER+"&sslmode=require",READER+"&options=-c%20role=postgres",
    READER+"&sslrootcert=a&sslrootcert=b",READER+"#fragment",READER.replace(":5432",":7777"),
    READER.replace("sportsbet_dashboard.projectref","postgres.projectref"),READER.replace("postgres?","?"),
    READER.replace("sportsbet_dashboard.projectref","sportsbet_worker.projectref"),
])
def test_connection_settings_cannot_override_tls_or_identity(reader):
    with pytest.raises(provisioner.ProvisionError):provisioner.writer_url(reader,OWNER,"generated-password")

@pytest.mark.parametrize("owner",[
    OWNER.replace("postgres.projectref","postgres.otherref"),OWNER.replace("us-west-1","us-east-1"),
    OWNER.replace("/postgres?","/foreign?"),OWNER.replace("verify-full","require"),
])
def test_owner_and_reader_must_point_to_same_project(owner):
    with pytest.raises(provisioner.ProvisionError):provisioner.writer_url(READER,owner,"generated-password")

def test_writer_url_replaces_credentials_and_uses_transaction_pool():
    url=provisioner.writer_url(READER,OWNER,"p@ss:/word?")
    split=urlsplit(url)
    assert split.username=="sportsbet_waitlist_writer.projectref" and split.port==6543
    assert unquote(split.password)=="p@ss:/word?" and split.query=="sslmode=verify-full"
    direct="postgresql://sportsbet_dashboard:fixture-reader@db.example.com:5432/postgres?sslmode=verify-full"
    assert urlsplit(provisioner.writer_url(direct,direct.replace("sportsbet_dashboard","postgres"),"pwd")).username==provisioner.ROLE

@pytest.mark.parametrize("changes",[
    {"type":"encrypted"},{"target":["preview"]},{"target":["production","preview"]},
    {"gitBranch":"master"},{"customEnvironmentIds":["foreign"]},{"comment":"unmanaged"},
    {"key":"DATABASE_URL"},
])
def test_existing_setting_must_be_managed_and_production_only(changes):
    entry={"key":provisioner.KEY,"type":"sensitive","target":["production"],"comment":provisioner.MARKER+"a"*64}
    with pytest.raises(provisioner.ProvisionError):provisioner.managed_entry(entry|changes)

def test_redirects_never_forward_token():
    with pytest.raises(provisioner.ProvisionError):provisioner.NoRedirect().redirect_request(None,None,302,"",{},"https://foreign.invalid")

@pytest.fixture
def database():
    url=os.environ.get("SPORTSBET_PRIVATE_ACCESS_TEST_URL")
    if not url:pytest.skip("Explicit disposable database required")
    assert urlsplit(url).hostname in ("localhost","127.0.0.1")
    name="waitlist_provision_"+uuid.uuid4().hex
    split=urlsplit(url);isolated=urlunsplit(split._replace(path="/"+name))
    with psycopg.connect(url,autocommit=True) as admin:
        # Every test owns its database; the cluster-scoped role is never reused.
        assert not admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(provisioner.ROLE,)).fetchone()
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    with psycopg.connect(isolated,autocommit=True) as conn:
        spec=importlib.util.spec_from_file_location("waitlist_migration",Path("alembic/versions/0046_private_waitlist.py"))
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        class Operations:
            def execute(self,statement):conn.execute(statement)
        migration.op=Operations();migration.upgrade()
        conn.execute("CREATE TABLE alembic_version(version_num text)")
        conn.execute("INSERT INTO alembic_version VALUES (%s)",(provisioner.HEAD,))
        conn.execute("CREATE TABLE public.dashboard_fixture(private_payload text)")
        conn.execute("INSERT INTO public.dashboard_fixture VALUES ('private')")
    try:yield isolated
    finally:
        with psycopg.connect(url,autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
            admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(provisioner.ROLE)))
            admin.execute("DROP ROLE IF EXISTS waitlist_fixture_extra")

def execute(database,provider=None,login=None):
    provider=provider or Provider()
    def local_connect(_):return provisioner.connect(database)
    def local_login(value):
        actual=urlsplit(value);local=urlsplit(database)
        netloc=f"{actual.username.split('.')[0]}:{actual.password}@{local.hostname}:{local.port or 5432}"
        provisioner.verify_login(urlunsplit(local._replace(netloc=netloc)))
    result=provisioner.provision(ENV,provider,local_connect,login or local_login)
    return result,provider

def test_new_login_is_verified_signup_and_counters_rollback_and_reruns_do_not_rotate(database):
    result,provider=execute(database)
    assert "login verified" in result and provider.calls.count("create")==1
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT count(*) FROM private_access.waitlist").fetchone()==(0,)
        assert conn.execute("SELECT count(*) FROM private_access.waitlist_limits").fetchone()==(0,)
        verifier=conn.execute("SELECT rolpassword FROM pg_authid WHERE rolname=%s",(provisioner.ROLE,)).fetchone()[0]
        assert verifier.startswith("SCRAM-SHA-256$")
        marker=provisioner.role_marker(conn);provisioner.verify_permissions(conn,marker)
    def no_login(_):pytest.fail("existing sensitive credential must not be read or rotated")
    repeated,_=execute(database,provider,no_login)
    assert "Existing managed" in repeated and provider.calls.count("create")==1
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT rolpassword FROM pg_authid WHERE rolname=%s",(provisioner.ROLE,)).fetchone()[0]==verifier
    bad=urlsplit(database);netloc=f"{provisioner.ROLE}:wrong-password@{bad.hostname}:{bad.port or 5432}"
    with pytest.raises(psycopg.OperationalError):provisioner.verify_login(urlunsplit(bad._replace(netloc=netloc)))

@pytest.mark.parametrize("drift",[
    "GRANT SELECT ON public.dashboard_fixture TO PUBLIC",
    "GRANT SELECT(private_payload) ON public.dashboard_fixture TO sportsbet_waitlist_writer",
    "ALTER ROLE sportsbet_waitlist_writer CREATEDB",
    "ALTER ROLE sportsbet_waitlist_writer INHERIT",
    "GRANT CREATE ON SCHEMA public TO PUBLIC",
    "CREATE ROLE waitlist_fixture_extra NOLOGIN; GRANT waitlist_fixture_extra TO sportsbet_waitlist_writer WITH INHERIT FALSE, SET TRUE",
    "CREATE ROLE waitlist_fixture_extra NOLOGIN; GRANT sportsbet_waitlist_writer TO waitlist_fixture_extra",
    "CREATE SEQUENCE public.private_sequence; GRANT USAGE ON SEQUENCE public.private_sequence TO sportsbet_waitlist_writer",
    "CREATE FUNCTION public.leaky() RETURNS integer LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'",
    "ALTER FUNCTION private_access.join_waitlist(text) SET search_path = public",
    "REVOKE EXECUTE ON FUNCTION private_access.join_waitlist(text) FROM sportsbet_waitlist_writer",
    "CREATE OR REPLACE FUNCTION private_access.join_waitlist(address text) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS 'BEGIN RETURN true; END'",
    "ALTER FUNCTION private_access.join_waitlist(text) OWNER TO sportsbet_waitlist_writer",
])
def test_existing_credential_rejects_effective_privilege_drift_without_repair_or_rotation(database,drift):
    _,provider=execute(database)
    with psycopg.connect(database,autocommit=True) as conn:
        original=conn.execute("SELECT rolpassword FROM pg_authid WHERE rolname=%s",(provisioner.ROLE,)).fetchone()
        conn.execute(drift)
    with pytest.raises(provisioner.ProvisionError):execute(database,provider)
    assert provider.calls.count("create")==1
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT rolpassword FROM pg_authid WHERE rolname=%s",(provisioner.ROLE,)).fetchone()==original

def test_public_grants_abort_first_creation_before_commit_or_secret_write(database):
    with psycopg.connect(database,autocommit=True) as conn:conn.execute("GRANT SELECT ON public.dashboard_fixture TO PUBLIC")
    provider=Provider()
    with pytest.raises(provisioner.ProvisionError):execute(database,provider)
    assert "create" not in provider.calls
    with psycopg.connect(database) as conn:assert not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(provisioner.ROLE,)).fetchone()

@pytest.mark.parametrize("mode",["failed","ambiguous"])
def test_interrupted_provider_write_is_reconciled_without_overwriting_or_rotating(database,mode):
    provider=Provider();provider.mode=mode
    with pytest.raises(RuntimeError):execute(database,provider)
    with psycopg.connect(database) as conn:original=conn.execute("SELECT rolpassword FROM pg_authid WHERE rolname=%s",(provisioner.ROLE,)).fetchone()
    if mode=="ambiguous":assert "Existing managed" in execute(database,provider)[0]
    else:
        with pytest.raises(provisioner.ProvisionError,match="refusing rotation"):execute(database,provider)
    assert provider.calls.count("create")==1
    with psycopg.connect(database) as conn:assert conn.execute("SELECT rolpassword FROM pg_authid WHERE rolname=%s",(provisioner.ROLE,)).fetchone()==original

def test_failed_login_never_publishes_credentials_or_retries_with_password_rotation(database):
    def bad(_):raise RuntimeError("simulated wrong login")
    provider=Provider()
    with pytest.raises(RuntimeError):execute(database,provider,bad)
    assert "create" not in provider.calls
    with pytest.raises(provisioner.ProvisionError,match="refusing rotation"):execute(database,provider)

def test_unmanaged_existing_role_is_not_repurposed(database):
    with psycopg.connect(database,autocommit=True) as conn:conn.execute("CREATE ROLE sportsbet_waitlist_writer NOLOGIN")
    provider=Provider()
    with pytest.raises(provisioner.ProvisionError,match="refusing rotation"):execute(database,provider)
    assert "create" not in provider.calls
    with psycopg.connect(database) as conn:assert conn.execute("SELECT rolcanlogin FROM pg_roles WHERE rolname=%s",(provisioner.ROLE,)).fetchone()==(False,)

def test_wrong_schema_never_creates_role(database):
    with psycopg.connect(database,autocommit=True) as conn:conn.execute("UPDATE alembic_version SET version_num='old'")
    provider=Provider()
    with pytest.raises(provisioner.ProvisionError,match="migration head"):execute(database,provider)
    assert "create" not in provider.calls
    with psycopg.connect(database) as conn:assert not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(provisioner.ROLE,)).fetchone()


def test_non_superuser_owner_automatic_admin_membership_is_not_runtime_access(database):
    with psycopg.connect(database,autocommit=True) as conn:
        conn.execute("CREATE ROLE waitlist_fixture_extra NOLOGIN NOINHERIT CREATEROLE")
        conn.execute("ALTER SCHEMA private_access OWNER TO waitlist_fixture_extra")
        for table in ('waitlist','waitlist_limits'):
            conn.execute(sql.SQL('ALTER TABLE private_access.{} OWNER TO waitlist_fixture_extra').format(sql.Identifier(table)))
        conn.execute("ALTER FUNCTION private_access.join_waitlist(text) OWNER TO waitlist_fixture_extra")
        conn.execute("GRANT SELECT ON alembic_version TO waitlist_fixture_extra")
    def local_connection(_):
        conn=provisioner.connect(database)
        conn.execute("SET ROLE waitlist_fixture_extra")
        return conn
    def local_login(value):
        actual=urlsplit(value);local=urlsplit(database)
        netloc=f"{actual.username.split('.')[0]}:{actual.password}@{local.hostname}:{local.port or 5432}"
        provisioner.verify_login(urlunsplit(local._replace(netloc=netloc)))
    provider=Provider()
    assert 'login verified' in provisioner.provision(ENV,provider,local_connection,local_login)
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT admin_option,inherit_option,set_option FROM pg_auth_members WHERE roleid=(SELECT oid FROM pg_roles WHERE rolname=%s)",(provisioner.ROLE,)).fetchall()==[(True,False,False)]
        assert not conn.execute("SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=%s)",(provisioner.ROLE,)).fetchone()


def test_dedicated_writer_against_complete_application_migration_chain(database):
    import alembic.command
    import alembic.config
    with psycopg.connect(database,autocommit=True) as conn:
        conn.execute("DROP SCHEMA private_access CASCADE")
        conn.execute("TRUNCATE alembic_version")
    cfg=alembic.config.Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url",database.replace("postgresql://","postgresql+psycopg://",1))
    alembic.command.upgrade(cfg,"head")
    result,provider=execute(database)
    assert 'login verified' in result
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','analytics') AND c.relkind IN ('r','v','p')").fetchone()[0]>30
        provisioner.verify_permissions(conn,provisioner.managed_entry(provider.values[0]))


@pytest.mark.parametrize("team,project",[
    ({"id":provisioner.TEAM,"billing":{"plan":"pro"}}, {"id":provisioner.PROJECT,"accountId":provisioner.TEAM,"rootDirectory":"frontend"}),
    ({"id":"foreign","billing":{"plan":"hobby"}}, {"id":provisioner.PROJECT,"accountId":provisioner.TEAM,"rootDirectory":"frontend"}),
    ({"id":provisioner.TEAM,"billing":{"plan":"hobby"}}, {"id":"foreign","accountId":provisioner.TEAM,"rootDirectory":"frontend"}),
    ({"id":provisioner.TEAM,"billing":{"plan":"hobby"}}, {"id":provisioner.PROJECT,"accountId":"foreign","rootDirectory":"frontend"}),
    ({"id":provisioner.TEAM,"billing":{"plan":"hobby"}}, {"id":provisioner.PROJECT,"accountId":provisioner.TEAM,"rootDirectory":"other"}),
])
def test_provider_identity_or_paid_plan_is_rejected(team,project):
    provider=provisioner.Vercel("fixture-token")
    provider.request=lambda path:team if path.startswith('/v2/teams/') else project
    with pytest.raises(provisioner.ProvisionError):provider.attest()

def test_provider_requests_are_fixed_https_create_only_and_never_decrypt():
    import json
    requests=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,_):return json.dumps({"envs":[],"created":{},"failed":[]}).encode()
    class Opener:
        def open(self,request,timeout):
            requests.append((request,timeout));return Response()
    provider=provisioner.Vercel("fixture-token");provider.opener=Opener()
    assert provider.entries()==[]
    provider.create("fixture-writer-url",provisioner.MARKER+"a"*64)
    assert len(requests)==2
    assert all(urlsplit(req.full_url).hostname=='api.vercel.com' and urlsplit(req.full_url).scheme=='https' and timeout==15 for req,timeout in requests)
    assert requests[0][0].get_method()=='GET' and 'decrypt=false' in requests[0][0].full_url
    request=requests[1][0]
    assert request.get_method()=='POST' and 'upsert' not in request.full_url
    payload=json.loads(request.data)
    assert payload=={"key":provisioner.KEY,"value":"fixture-writer-url","type":"sensitive","target":["production"],"comment":provisioner.MARKER+"a"*64}
    assert request.get_header('Authorization')=='Bearer fixture-token'

@pytest.mark.parametrize("data",[{"envs":[{"key":provisioner.KEY},{"key":provisioner.KEY}]},{"envs":None}])
def test_ambiguous_environment_metadata_is_rejected(data):
    provider=provisioner.Vercel("fixture-token");provider.request=lambda _:data
    with pytest.raises(provisioner.ProvisionError):provider.entries()

def test_generic_cli_exception_cannot_log_credentials(capsys,monkeypatch):
    # Exercise the actual CLI error path in-process without any network operation.
    import runpy
    monkeypatch.setattr(os,'environ',ENV)
    monkeypatch.setattr('sys.argv',['ops/provision_waitlist.py'])
    def failure(_):raise RuntimeError('DO-NOT-LOG-PRIVATE-URL-OR-TOKEN')
    monkeypatch.setattr(provisioner.Vercel,'attest',failure)
    # run_path defines a fresh class; intercept the shared urllib opener instead.
    monkeypatch.setattr('urllib.request.build_opener',lambda *_:failure(None))
    with pytest.raises(SystemExit) as stopped:runpy.run_path('ops/provision_waitlist.py',run_name='__main__')
    captured=capsys.readouterr()
    assert stopped.value.code==1 and 'DO-NOT-LOG' not in captured.err and 'failed' in captured.err
