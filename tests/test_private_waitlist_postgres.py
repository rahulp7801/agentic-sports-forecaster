"""Owner-only signup storage is verified only on an explicitly disposable database."""
import importlib.util
import os
from pathlib import Path

import psycopg
from psycopg import sql
import pytest

@pytest.mark.skipif(not os.environ.get('SPORTSBET_PRIVATE_ACCESS_TEST_URL'), reason='Disposable access database required')
def test_private_waitlist_acl_limits_idempotency_and_downgrade_retention():
    url=os.environ['SPORTSBET_PRIVATE_ACCESS_TEST_URL']
    # Explicit loopback-only fixture boundary; never run this destructive schema fixture on hosting.
    from urllib.parse import urlsplit, urlunsplit
    import uuid
    assert urlsplit(url).hostname in ('localhost','127.0.0.1')
    spec=importlib.util.spec_from_file_location('waitlist_migration',Path('alembic/versions/0046_private_waitlist.py'))
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    database='access_waitlist_'+uuid.uuid4().hex
    with psycopg.connect(url,autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    split=urlsplit(url);isolated=urlunsplit(split._replace(path='/'+database))
    with psycopg.connect(isolated,autocommit=True) as conn:
        created_writer = not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',('sportsbet_waitlist_writer',)).fetchone()
        class Operations:
            def execute(self,statement):conn.execute(statement)
        migration.op=Operations()
        for role in ('anon','authenticated','sportsbet_dashboard','sportsbet_worker','sportsbet_waitlist_writer'):
            if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():
                conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOINHERIT').format(sql.Identifier(role)))
        migration.upgrade()
        try:
            conn.execute(Path('ops/provision_waitlist.sql').read_text())
            for role in ('anon','authenticated','sportsbet_dashboard','sportsbet_worker'):
                conn.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
                for query in ("SELECT * FROM private_access.waitlist", "SELECT private_access.join_waitlist('visitor@example.com')"):
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute(query)
                conn.execute('RESET ROLE')
            conn.execute('SET ROLE sportsbet_waitlist_writer')
            for query in ('SELECT * FROM private_access.waitlist', 'SELECT * FROM private_access.waitlist_limits',
                          "INSERT INTO private_access.waitlist(email) VALUES ('b@example.com')"):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute(query)
            assert conn.execute("SELECT private_access.join_waitlist('visitor@example.com')").fetchone()==(True,)
            assert conn.execute("SELECT private_access.join_waitlist('visitor@example.com')").fetchone()==(True,)
            with pytest.raises(psycopg.errors.RaiseException):conn.execute("SELECT private_access.join_waitlist('bad address')")
            conn.execute('RESET ROLE')
            assert conn.execute('SELECT count(*) FROM private_access.waitlist').fetchone()==(1,)
            assert conn.execute('SELECT consent_version FROM private_access.waitlist').fetchone()==('access-update-v1',)
            conn.execute("UPDATE private_access.waitlist_limits SET requests=30 WHERE period='minute'")
            conn.execute('SET ROLE sportsbet_waitlist_writer')
            assert conn.execute("SELECT private_access.join_waitlist('blocked@example.com')").fetchone()==(False,)
            conn.execute('RESET ROLE')
            assert conn.execute('SELECT count(*) FROM private_access.waitlist').fetchone()==(1,)
            conn.execute("UPDATE private_access.waitlist_limits SET requests=1 WHERE period='minute'")
            conn.execute("UPDATE private_access.waitlist_limits SET requests=500 WHERE period='day'")
            conn.execute('SET ROLE sportsbet_waitlist_writer')
            assert conn.execute("SELECT private_access.join_waitlist('blocked@example.com')").fetchone()==(False,)
            conn.execute('RESET ROLE')
            with pytest.raises(psycopg.errors.RaiseException,match='retained waitlist'):migration.downgrade()
            conn.execute('DELETE FROM private_access.waitlist')
            migration.downgrade()
        finally:
            conn.execute('RESET ROLE')
            conn.execute('DROP SCHEMA IF EXISTS private_access CASCADE')
    with psycopg.connect(url,autocommit=True) as admin:
        admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(database)))
        if created_writer:admin.execute('DROP ROLE sportsbet_waitlist_writer')
