"""Forward NFL card history, correction chronology and owner-only archive checks."""
from datetime import datetime, timedelta, timezone
import os
import secrets

import psycopg
import pytest

from sportsbet.db.access import provision_roles, apply_access, READER, WORKER
from sportsbet.ingestion.provenance import stat_row_sha256
from tests.test_nfl_history_supplements import game, primary

pytestmark = pytest.mark.skipif(not os.environ.get('SPORTSBET_TEST_DATABASE_URL'),
    reason='Disposable PostgreSQL required')


def connect():
    return psycopg.connect(os.environ['SPORTSBET_TEST_DATABASE_URL'].replace(
        'postgresql+psycopg://','postgresql://',1))


def insert(conn, table, row):
    conn.execute('INSERT INTO public.'+table+' ('+','.join(row)+') VALUES ('
        +','.join(['%s']*len(row))+')', tuple(row.values()))


def archive_count(conn, player_id):
    return conn.execute('SELECT count(*) FROM public.nfl_primary_revisions WHERE player_id=%s',
        (player_id,)).fetchone()[0]


def displayed(conn, player_id, cutoff):
    return conn.execute("""SELECT payload,source_row FROM (
        SELECT DISTINCT ON (sport,COALESCE(player_id,player_name),game_key)
            payload,source_row,game_date,player_name,game_key
        FROM public.dashboard_nfl_core_gamelogs_asof
        WHERE sport='nfl' AND player_id=%s AND game_date<'2026-10-06'
            AND record_available_at<=%s
        ORDER BY sport,COALESCE(player_id,player_name),game_key,
            record_available_at DESC NULLS LAST
        ) versions ORDER BY game_date DESC,player_name,game_key LIMIT 20""",
        (player_id,cutoff)).fetchall()


def test_two_corrections_retain_each_cutoff_and_never_backdate_card_evidence():
    row=primary(player_name='History fixture',passing_yards=250,rushing_yards=3)
    with connect() as conn:
        try:
            insert(conn,'games',game()); insert(conn,'player_stats',row)
            initial=conn.execute('SELECT source_observed_at FROM public.player_stats WHERE player_id=%s',
                (row['player_id'],)).fetchone()[0]
            assert displayed(conn,row['player_id'],initial-timedelta(microseconds=1))==[]
            first=displayed(conn,row['player_id'],initial)
            assert len(first)==1 and first[0][0]['pass_yds']==250
            # Even a correction submitted with the original observation time
            # cannot silently change the historical card at that old cutoff.
            for value in (200,210):
                corrected=row|dict(passing_yards=value)
                digest=stat_row_sha256('nfl',corrected)
                conn.execute('UPDATE public.player_stats SET passing_yards=%s,'
                    'source_record_sha256=%s WHERE player_id=%s',
                    (value,digest,row['player_id']))
                assert conn.execute('SELECT passing_yards,source_observed_at '
                    'FROM public.player_stats WHERE player_id=%s',(row['player_id'],)).fetchone()==(value,initial)
                now=conn.execute('SELECT clock_timestamp()').fetchone()[0]
                current=displayed(conn,row['player_id'],now)
                assert len(current)==1 and current[0][0]['pass_yds']==value
                assert stat_row_sha256('nfl',current[0][1])==current[0][1]['source_record_sha256']
                assert displayed(conn,row['player_id'],initial)==first
                if value==200:
                    middle_time=now; middle=current
            assert displayed(conn,row['player_id'],middle_time)==middle
            assert archive_count(conn,row['player_id'])==2
            dates=conn.execute('SELECT record_available_at,replaced_at FROM '
                'public.nfl_primary_revisions WHERE player_id=%s ORDER BY revision_id',
                (row['player_id'],)).fetchall()
            assert dates[0][0]==initial and dates[1][0]==dates[0][1]
        finally:
            conn.rollback()


def test_bundle_refresh_schedule_enrichment_and_unproven_rows_do_not_archive():
    row=primary(player_name='History fixture',passing_yards=250,rushing_yards=3)
    with connect() as conn:
        try:
            insert(conn,'games',game()); insert(conn,'player_stats',row)
            conn.execute("UPDATE public.player_stats SET source_sha256=repeat('f',64),"
                "opponent_team='JAX',home_away='home' WHERE player_id=%s",(row['player_id'],))
            assert archive_count(conn,row['player_id'])==0
            assert displayed(conn,row['player_id'],datetime.now(timezone.utc))[0][0]['pass_yds']==250
            # Simulate a pre-provenance legacy row. NOT VALID constraints can
            # retain such old rows, but still require every new update to prove
            # its source. The trigger must not manufacture an archive for it.
            definition=conn.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid='public.player_stats'::regclass "
                "AND conname='ck_player_stats_source_evidence'").fetchone()[0]
            conn.execute('ALTER TABLE public.player_stats DROP CONSTRAINT ck_player_stats_source_evidence')
            legacy=row|dict(player_id='00-0000001',source_provider=None,source_sha256=None,
                source_record_sha256=None,source_observed_at=None)
            insert(conn,'player_stats',legacy)
            conn.execute('ALTER TABLE public.player_stats ADD CONSTRAINT ck_player_stats_source_evidence '+definition)
            proven=legacy|dict(passing_yards=200)
            conn.execute('UPDATE public.player_stats SET passing_yards=200,source_provider=%s,'
                'source_sha256=%s,source_record_sha256=%s,source_observed_at=%s WHERE player_id=%s',
                ('nflverse','a'*64,stat_row_sha256('nfl',proven),row['source_observed_at'],legacy['player_id']))
            assert archive_count(conn,row['player_id'])==archive_count(conn,legacy['player_id'])==0
        finally:
            conn.rollback()


def test_worker_correction_archives_without_direct_private_table_or_function_access():
    row=primary(player_name='History fixture',passing_yards=250,rushing_yards=3)
    with connect() as conn:
        try:
            for role in ('anon','authenticated'):
                if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():
                    conn.execute('CREATE ROLE '+role+' NOLOGIN')
            provision_roles(conn,{role:secrets.token_urlsafe(32) for role in (READER,WORKER)})
            insert(conn,'games',game())
            conn.execute('SET LOCAL ROLE sportsbet_worker')
            insert(conn,'player_stats',row)
            corrected=row|dict(passing_yards=200)
            conn.execute('UPDATE public.player_stats SET passing_yards=200,source_record_sha256=%s WHERE player_id=%s',
                (stat_row_sha256('nfl',corrected),row['player_id']))
            conn.execute('RESET ROLE')
            assert archive_count(conn,row['player_id'])==1
            for role in ('anon','authenticated',READER,WORKER):
                assert not conn.execute('SELECT has_table_privilege(%s,%s,%s)',
                    (role,'public.nfl_primary_revisions','SELECT,INSERT,UPDATE,DELETE,TRUNCATE')).fetchone()[0]
                assert not conn.execute('SELECT has_sequence_privilege(%s,%s,%s)',
                    (role,'public.nfl_primary_revisions_revision_id_seq','USAGE,SELECT,UPDATE')).fetchone()[0]
                assert not conn.execute('SELECT has_function_privilege(%s,%s,%s)',
                    (role,'public.archive_nfl_primary_revision()','EXECUTE')).fetchone()[0]
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    with conn.transaction():
                        conn.execute('SET LOCAL ROLE '+role)
                        conn.execute('SELECT * FROM public.nfl_primary_revisions')
            conn.execute('SET LOCAL ROLE sportsbet_dashboard')
            assert len(displayed(conn,row['player_id'],datetime.now(timezone.utc)))==1
            conn.execute('RESET ROLE')
            conn.execute('GRANT ALL ON public.nfl_primary_revisions TO anon,sportsbet_dashboard,sportsbet_worker')
            apply_access(conn)
            for role in ('anon',READER,WORKER):
                assert not conn.execute('SELECT has_table_privilege(%s,%s,%s)',
                    (role,'public.nfl_primary_revisions','SELECT,INSERT,UPDATE,DELETE,TRUNCATE')).fetchone()[0]
            definition=conn.execute("SELECT prosecdef,proconfig FROM pg_proc WHERE oid="
                "'public.archive_nfl_primary_revision()'::regprocedure").fetchone()
            assert definition==(True,['search_path=pg_catalog'])
        finally:
            conn.rollback()


def test_populated_evidence_archive_refuses_destructive_downgrade():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import DBAPIError
    spec=importlib.util.spec_from_file_location('nfl_revision_migration',
        Path('alembic/versions/0045_nfl_core_history_revisions.py'))
    migration=importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine=create_engine(os.environ['SPORTSBET_TEST_DATABASE_URL'])
    row=primary(player_name='History fixture',passing_yards=250,rushing_yards=3)
    try:
        with engine.connect() as conn:
            transaction=conn.begin()
            try:
                conn.execute(text('INSERT INTO public.player_stats ('+','.join(row)+') VALUES ('
                    +','.join(':'+key for key in row)+')'),row)
                conn.execute(text('UPDATE public.player_stats SET passing_yards=200 WHERE player_id=:id'),
                    {'id':row['player_id']})
                with Operations.context(MigrationContext.configure(conn)):
                    with pytest.raises(DBAPIError,match='Retained NFL evidence prevents downgrade'):
                        with conn.begin_nested():
                            migration.downgrade()
                assert conn.execute(text('SELECT count(*) FROM public.nfl_primary_revisions WHERE player_id=:id'),
                    {'id':row['player_id']}).scalar_one()==1
                assert conn.execute(text('SELECT count(*) FROM public.player_stats WHERE player_id=:id'),
                    {'id':row['player_id']}).scalar_one()==1
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
