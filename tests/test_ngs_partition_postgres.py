"""Complete tracking versions, exact forecast replay and restricted replacements."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import runpy

from alembic.migration import MigrationContext
from alembic.operations import Operations
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import pytest
import sqlalchemy as sa

from sportsbet.db.access import apply_access, provision_roles, READER, WORKER, NGS_REPLACE_FUNCTION
from sportsbet.ingestion.ngs import normalize_asset, ingest_ngs_seasons, METRIC_COLUMNS
from sportsbet.ingestion.provenance import row_sha256
from sportsbet.prop.ngs_evidence import load_ngs_evidence
from tests.test_ngs_ingestion import parquet, passing_rows

pytestmark=pytest.mark.skipif(not os.environ.get('SPORTSBET_TEST_DATABASE_URL'),
    reason='Disposable PostgreSQL required')


def records(weeks=(1,2), value=2.765, kind='passing', observed=None):
    observed=observed or datetime.now(timezone.utc)-timedelta(minutes=5)
    base=passing_rows()[1]|dict(avg_time_to_throw=value)
    if kind!='passing':
        base={key:base[key] for key in ('season','week','player_gsis_id','team_abbr','player_position')}
        base['player_position']='WR' if kind=='receiving' else 'RB'
        base.update({key:3 if key in ('targets','receptions','rush_attempts') else value
                     for key in METRIC_COLUMNS[kind]})
    return normalize_asset(parquet([base|dict(week=w) for w in weeks]),2026,kind,observed)[0]


def replace(conn, rows):
    row=rows[0]
    payload=[r|dict(source_observed_at=r['source_observed_at'].isoformat()) for r in rows]
    return conn.execute('SELECT version_id,unchanged FROM public.replace_ngs_partition(%s,%s,%s,%s,%s)',
        (row['season'],row['stat_type'],row['source_sha256'],row['source_observed_at'],Jsonb(payload))).fetchone()


@pytest.fixture
def conn():
    with psycopg.connect(os.environ['SPORTSBET_TEST_DATABASE_URL'].replace(
            'postgresql+psycopg://','postgresql://',1)) as connection:
        try:
            yield connection
        finally:
            connection.rollback()


class EvidencePool:
    """Run the real async reader SQL inside the rollback-only fixture transaction."""
    def __init__(self,conn):self.conn=conn
    def acquire(self):return self
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    def cursor(self,query,args):
        sql=re.sub(r'\$(\d+)',lambda m:'%(arg'+m[1]+')s',query)
        cursor=self.conn.cursor(row_factory=dict_row)
        cursor.execute(sql,{'arg'+str(i):arg for i,arg in enumerate(args,1)})
        return cursor
    async def fetch(self,query,*args):
        with self.cursor(query,args) as cursor:return cursor.fetchall()
    async def fetchrow(self,query,*args):
        with self.cursor(query,args) as cursor:return cursor.fetchone()
    async def fetchval(self,query,*args):
        with self.cursor(query,args) as cursor:return next(iter(cursor.fetchone().values()))


def schedule(conn):
    conn.execute("""INSERT INTO games(game_id,season,week,game_date,home_team,away_team)
        VALUES ('tracking-fixture',2026,3,'2026-09-20','SEA','DEN')""")


async def displayed(conn,cutoff,refs=None):
    return await load_ngs_evidence(EvidencePool(conn),player_gsis_id='00-0031234',
        season=2026,game_date=date(2026,9,20),team='SEA',prop_type='pass_yds',
        observed_before=cutoff,partition_refs=refs)


def available(conn,version):
    return conn.execute('SELECT recorded_at FROM ngs_partition_versions WHERE version_id=%s',(version,)).fetchone()[0]


@pytest.mark.asyncio
async def test_full_partition_corrections_removals_and_pinned_replay(conn):
    schedule(conn)
    first,_=replace(conn,records())
    first_at=available(conn,first)
    original=await displayed(conn,first_at)
    assert original['sample_weeks']==2 and original['metrics']['avg_time_to_throw']==2.77
    assert await displayed(conn,first_at-timedelta(microseconds=1)) is None
    second,_=replace(conn,records(weeks=(1,),value=3.255))
    middle_at=available(conn,second)
    middle=await displayed(conn,middle_at)
    assert middle['sample_weeks']==1 and middle['metrics']['avg_time_to_throw']==3.26
    assert middle['sample_periods']==[dict(season=2026,week=1,team='SEA')]
    third,_=replace(conn,records(value=4.125))
    latest_at=available(conn,third)
    latest=await displayed(conn,latest_at)
    assert latest['sample_weeks']==2 and latest['metrics']['avg_time_to_throw']==4.13
    assert await displayed(conn,first_at)==original
    assert await displayed(conn,middle_at)==middle
    replay=await displayed(conn,latest_at,original['partition_refs'])
    for key in ('metrics','sample_periods','source_sha256','partition_refs'):
        assert replay[key]==original[key]
    assert conn.execute('SELECT count(*) FROM ngs_partition_rows').fetchone()[0]==3
    assert conn.execute('SELECT count(*) FROM ngs_history_versions').fetchone()[0]==5


@pytest.mark.asyncio
async def test_removed_player_cannot_resurrect_from_an_older_partition(conn):
    schedule(conn)
    first,_=replace(conn,records())
    original=await displayed(conn,available(conn,first))
    other=[r|dict(player_gsis_id='00-0000001',source_sha256='e'*64) for r in records()]
    for row in other:
        keys=('season','week','player_gsis_id','team_abbr','player_position','stat_type')+METRIC_COLUMNS['passing']
        row['source_record_sha256']=row_sha256({k:row[k] for k in keys})
    second,_=replace(conn,other)
    cutoff=available(conn,second)
    assert await displayed(conn,cutoff) is None
    assert (await displayed(conn,cutoff,original['partition_refs']))['metrics']==original['metrics']


def test_same_payload_retry_preserves_ids_times_and_archive(conn):
    source=records()
    first,unchanged=replace(conn,source)
    before=conn.execute('SELECT to_jsonb(n) FROM ngs_stats n ORDER BY id').fetchall()
    retry=[r|dict(source_observed_at=r['source_observed_at']+timedelta(minutes=1)) for r in source]
    assert replace(conn,retry)==(first,True)
    assert unchanged is False
    assert conn.execute('SELECT to_jsonb(n) FROM ngs_stats n ORDER BY id').fetchall()==before
    assert conn.execute('SELECT count(*) FROM ngs_partition_versions').fetchone()[0]==1
    assert conn.execute('SELECT count(*) FROM ngs_partition_rows').fetchone()[0]==0
    digest=hashlib.sha256('\n'.join(sorted(r['source_record_sha256'] for r in source)).encode()).hexdigest()
    assert conn.execute('SELECT record_set_sha256 FROM ngs_partition_versions').fetchone()[0]==digest


def test_changed_bundle_with_same_metrics_retains_old_commitments(conn):
    source=records();first,_=replace(conn,source)
    second,_=replace(conn,[r|dict(source_sha256='b'*64) for r in source])
    assert first!=second
    assert conn.execute('SELECT count(*) FROM ngs_partition_rows WHERE version_id=%s',(first,)).fetchone()[0]==2
    assert conn.execute('SELECT DISTINCT source_sha256 FROM ngs_stats').fetchall()==[('b'*64,)]


@pytest.mark.parametrize('damage',['old','future','duplicate','extra','partition','provider','url','missing','overflow'])
def test_invalid_refresh_rolls_back_without_changing_any_version(conn,damage):
    source=records();replace(conn,source)
    before=conn.execute('SELECT to_jsonb(n) FROM ngs_history_versions n ORDER BY id').fetchall()
    bad=records(value=3.1)
    if damage=='old':bad=[r|dict(source_observed_at=source[0]['source_observed_at']-timedelta(days=1)) for r in bad]
    elif damage=='future':bad=[r|dict(source_observed_at=datetime.now(timezone.utc)+timedelta(days=1)) for r in bad]
    elif damage=='duplicate':bad.append(bad[0])
    elif damage=='extra':bad[0]['unrecognized_alpha']='fixture'
    elif damage=='partition':bad[1]['season']=2025
    elif damage=='provider':bad[1]['source_provider']='untrusted'
    elif damage=='url':bad[1]['source_url']='https://example.com/fixture'
    elif damage=='missing':bad[1]['avg_time_to_throw']=None
    elif damage=='overflow':bad[1]['attempts']=32768
    with pytest.raises(psycopg.Error):
        with conn.transaction():replace(conn,bad)
    assert conn.execute('SELECT to_jsonb(n) FROM ngs_history_versions n ORDER BY id').fetchall()==before
    assert conn.execute('SELECT count(*) FROM ngs_partition_versions').fetchone()[0]==1
    assert conn.execute('SELECT count(*) FROM ngs_partition_rows').fetchone()[0]==0


def test_permissions_and_repair_keep_raw_versions_owner_only(conn):
    for role in ('anon','authenticated'):
        if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():
            conn.execute('CREATE ROLE '+role+' NOLOGIN')
    if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(WORKER,)).fetchone():
        provision_roles(conn,{READER:'fixture-reader',WORKER:'fixture-worker'})
    else:apply_access(conn)
    # Repair an accidental grant, including direct mutation and function access.
    for role in (READER,WORKER,'anon','authenticated'):
        conn.execute('GRANT ALL ON ngs_partition_rows,ngs_partition_versions,ngs_history_versions,ngs_partition_catalog TO '+role)
        conn.execute('GRANT ALL ON SEQUENCE ngs_partition_versions_version_id_seq TO '+role)
        conn.execute('GRANT EXECUTE ON FUNCTION '+NGS_REPLACE_FUNCTION+' TO '+role)
    conn.execute('GRANT ALL ON ngs_stats TO '+WORKER)
    apply_access(conn)
    for role in (READER,WORKER,'anon','authenticated'):
        for table in ('ngs_partition_rows','ngs_partition_versions'):
            assert not conn.execute("SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')",
                (role,table)).fetchone()[0]
        assert not conn.execute("SELECT has_sequence_privilege(%s,'ngs_partition_versions_version_id_seq','USAGE,SELECT,UPDATE')",
            (role,)).fetchone()[0]
        assert conn.execute("SELECT has_function_privilege(%s,%s,'EXECUTE')",(role,NGS_REPLACE_FUNCTION)).fetchone()[0]==(role==WORKER)
        for table in ('ngs_history_versions','ngs_partition_catalog'):
            assert conn.execute("SELECT has_table_privilege(%s,%s,'SELECT')",(role,table)).fetchone()[0]==(role==WORKER)
    conn.execute('SET LOCAL ROLE '+WORKER)
    version,_=replace(conn,records())
    assert version>0
    for statement in ('INSERT INTO ngs_stats DEFAULT VALUES','UPDATE ngs_stats SET week=week',
                      'DELETE FROM ngs_stats','TRUNCATE ngs_stats','SELECT * FROM ngs_partition_rows',
                      'SELECT * FROM ngs_partition_versions'):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with conn.transaction():conn.execute(statement)
    conn.execute('RESET ROLE')


def test_real_ingester_retains_precision_and_retries_without_download(monkeypatch,pg_engine,tmp_path):
    from sportsbet.ingestion import ngs
    observed=datetime.now(timezone.utc)-timedelta(minutes=5)
    assets={kind:parquet([{k:v for k,v in r.items() if not k.startswith('source_') and k!='stat_type'}
        for r in records(kind=kind,observed=observed)]) for kind in METRIC_COLUMNS}
    monkeypatch.setattr(ngs,'load_asset',lambda client,kind,**kwargs:(assets[kind],observed,True))
    with pg_engine.connect() as connection:
        transaction=connection.begin()
        class BoundEngine:
            @contextmanager
            def begin(self):
                with connection.begin_nested():yield connection
        try:
            first=ingest_ngs_seasons([2026],BoundEngine(),cache_dir=tmp_path)
            retry=ingest_ngs_seasons([2026],BoundEngine(),cache_dir=tmp_path)
            assert all(a['cache_hit'] and not a['unchanged'] for a in first['assets'])
            assert all(a['unchanged'] for a in retry['assets'])
            assert [a['partition_version_id'] for a in first['assets']]==[a['partition_version_id'] for a in retry['assets']]
            for row in connection.execute(sa.text('SELECT * FROM ngs_stats')).mappings():
                keys=('season','week','player_gsis_id','team_abbr','player_position','stat_type')+METRIC_COLUMNS[row['stat_type']]
                assert row_sha256({k:row[k] for k in keys})==row['source_record_sha256']
        finally:transaction.rollback()


def migration():
    return runpy.run_path(str(Path('alembic/versions/0047_ngs_partition_versions.py')))


def test_migration_preserves_legacy_rows_and_grants_in_roles_first_order(pg_engine):
    with pg_engine.connect() as connection:
        transaction=connection.begin()
        try:
            with Operations.context(MigrationContext.configure(connection)):
                migration()['downgrade']()
            # Legacy rows have no partition pointer; backfill must not rehash or
            # rewrite their observed timestamps and unreplayable metrics.
            source=records()
            for row in source:
                connection.execute(sa.text('INSERT INTO ngs_stats ('+','.join(row)+') VALUES ('
                    +','.join(':'+k for k in row)+')'),row)
            before=connection.execute(sa.text('SELECT * FROM ngs_stats ORDER BY week')).mappings().all()
            if not connection.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname='sportsbet_worker'")).first():
                connection.execute(sa.text('CREATE ROLE sportsbet_worker NOLOGIN'))
            connection.execute(sa.text('GRANT SELECT,INSERT,UPDATE,DELETE ON ngs_stats TO sportsbet_worker'))
            if not connection.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname='anon'")).first():
                connection.execute(sa.text('CREATE ROLE anon NOLOGIN'))
            connection.execute(sa.text('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon'))
            connection.execute(sa.text('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon'))
            with Operations.context(MigrationContext.configure(connection)):
                migration()['upgrade']()
            rows=connection.execute(sa.text('SELECT * FROM ngs_stats ORDER BY week')).mappings().all()
            for old,new in zip(before,rows):
                assert all(new[k]==v for k,v in old.items())
            assert connection.execute(sa.text('SELECT normalization_version FROM ngs_partition_versions')).scalar_one()=='legacy-ngs-row-v1'
            assert not connection.execute(sa.text("SELECT has_table_privilege('sportsbet_worker','ngs_stats','INSERT,UPDATE,DELETE')")).scalar_one()
            for table in ('ngs_partition_versions','ngs_partition_rows','ngs_history_versions','ngs_partition_catalog'):
                assert not connection.execute(sa.text("SELECT has_table_privilege('anon',:table,'SELECT,INSERT,UPDATE,DELETE')"),{'table':table}).scalar_one()
            with Operations.context(MigrationContext.configure(connection)):
                migration()['downgrade']()
            assert connection.execute(sa.text('SELECT count(*) FROM ngs_stats')).scalar_one()==2
        finally:transaction.rollback()


def test_downgrade_refuses_retained_new_versions(pg_engine):
    with pg_engine.connect() as connection:
        transaction=connection.begin()
        try:
            rows=records()
            connection.execute(sa.text('SELECT * FROM replace_ngs_partition(2026,\'passing\',:hash,:observed,CAST(:payload AS jsonb))'),
                dict(hash=rows[0]['source_sha256'],observed=rows[0]['source_observed_at'],
                    payload=json.dumps([r|dict(source_observed_at=r['source_observed_at'].isoformat()) for r in rows])))
            with pytest.raises(sa.exc.ProgrammingError,match='Retained tracking versions'):
                with connection.begin_nested(),Operations.context(MigrationContext.configure(connection)):
                    migration()['downgrade']()
            assert connection.execute(sa.text('SELECT count(*) FROM ngs_stats')).scalar_one()==2
        finally:transaction.rollback()
