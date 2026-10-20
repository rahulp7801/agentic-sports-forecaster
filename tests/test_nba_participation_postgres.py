"""Actual source writers, cutoffs and append-only roles on disposable PostgreSQL."""
import asyncio
from datetime import date, datetime, timedelta, timezone
import os
import uuid
import runpy
from contextlib import contextmanager
from unittest.mock import MagicMock
from alembic.migration import MigrationContext
from alembic.operations import Operations

import pandas as pd
import psycopg
from psycopg import sql
import pytest
import sqlalchemy as sa

from sportsbet.db.access import apply_access, READER, WORKER
from sportsbet.ingestion.nba_participation import prepare_participation, store_participation
from sportsbet.ingestion.upsert import upsert_rows
from sportsbet.prop.injury_context import _nba_split
from tests.test_nba_participation import source_row

pytestmark=pytest.mark.skipif(not os.environ.get('SPORTSBET_TEST_DATABASE_URL'),reason='Disposable PostgreSQL required')


@pytest.fixture
def db():
    engine=sa.create_engine(os.environ['SPORTSBET_TEST_DATABASE_URL'])
    with engine.connect() as conn:
        tx=conn.begin()
        try:yield conn
        finally:tx.rollback()
    engine.dispose()


def write(conn,rows,complete=False):
    prepared=prepare_participation(rows)
    count=pd.DataFrame(rows).to_sql('nba_player_gamelogs',conn,if_exists='append',index=False,
        method=upsert_rows(['player_id','game_id'],preserve_observation_on_unchanged=True,
            skip_unchanged_updates=True))
    store_participation(conn,prepared,complete_season=rows[0]['season'] if complete else None)
    return count


def versions(conn,player,game):
    return conn.execute(sa.text('SELECT * FROM nba_participation_versions WHERE player_id=:p AND game_id=:g ORDER BY version_id'),dict(p=player,g=game)).mappings().all()


def fixture_rows():
    token=uuid.uuid4().hex[:12];subject=800000001;participant=800000002
    observed=datetime.now(timezone.utc)-timedelta(minutes=5)
    rows=[]
    for day,value in ((1,10),(2,30),(3,25)):
        rows.append(source_row(player_id=subject,player_name='Target '+token,game_id=token+str(day),
            game_date=date(2026,1,day),points=value,source_observed_at=observed))
        rows.append(source_row(player_id=participant,player_name='Context '+token,game_id=token+str(day),
            game_date=date(2026,1,day),minutes=20 if day<3 else 0,source_observed_at=observed))
    candidate=dict(player='Context '+token,status='Out',position='SG',team='LA',stat_team='LAC',relationship='teammate',unit='offense')
    return rows,subject,participant,candidate


class Adapter:
    def __init__(self,conn):self.conn=conn
    def query(self,statement,args):
        import re
        params={f'p{i+1}':v for i,v in enumerate(args)}
        return self.conn.execute(sa.text(re.sub(r'\$(\d+)',lambda m:':p'+m[1],statement)),params)
    async def fetch(self,statement,*args):return self.query(statement,args).mappings().all()
    async def fetchval(self,statement,*args):return self.query(statement,args).scalar_one()


def split(conn,subject,candidate,stamp=None):
    return asyncio.run(_nba_split(Adapter(conn),str(subject),2024,date(2026,9,30),'points',15.5,'over',candidate,stamp))


def test_unchanged_official_replay_skips_stat_tuple_update_and_retains_minutes_receipts(db):
    rows,_,participant,_=fixture_rows()
    assert write(db,rows)==len(rows)
    params=dict(p=participant,g=rows[1]['game_id'])
    before=db.execute(sa.text('SELECT ctid::text,xmin::text,to_jsonb(n) FROM nba_player_gamelogs n '
        'WHERE player_id=:p AND game_id=:g'),params).one()
    prior=versions(db,participant,rows[1]['game_id'])
    repeated=[r|dict(source_sha256='b'*64,
        source_observed_at=r['source_observed_at']+timedelta(seconds=1)) for r in rows]

    assert write(db,repeated)==0

    assert db.execute(sa.text('SELECT ctid::text,xmin::text,to_jsonb(n) FROM nba_player_gamelogs n '
        'WHERE player_id=:p AND game_id=:g'),params).one()==before
    assert versions(db,participant,rows[1]['game_id'])==prior
    # CTID distinguishes an UPDATE inside this same transaction; xmin alone does not.
    corrected=repeated[1]|dict(minutes=0)
    assert corrected['source_record_sha256']==rows[1]['source_record_sha256']
    assert write(db,[corrected])==1
    after=db.execute(sa.text('SELECT ctid::text,minutes,source_sha256,source_observed_at '
        'FROM nba_player_gamelogs WHERE player_id=:p AND game_id=:g'),params).one()
    assert after[0]!=before[0] and tuple(after[1:])==(0,'b'*64,corrected['source_observed_at'])
    assert len(versions(db,participant,rows[1]['game_id']))==2


def test_minutes_only_correction_preserves_earlier_comparison_and_first_retry_receipt(db):
    rows,subject,participant,candidate=fixture_rows();write(db,rows)
    original=split(db,subject,candidate)
    first=db.execute(sa.text('SELECT clock_timestamp()')).scalar_one()
    original=split(db,subject,candidate,first)
    assert original['active']['games']==2 and original['absent']['games']==1
    before=versions(db,participant,rows[3]['game_id'])[0]
    changed=rows[3]|dict(minutes=0,source_observed_at=rows[3]['source_observed_at']+timedelta(seconds=1))
    write(db,[changed]);later=db.execute(sa.text('SELECT clock_timestamp()')).scalar_one()
    assert split(db,subject,candidate,first)==original
    current=split(db,subject,candidate,later)
    assert current['active']['games']==1 and current['absent']['games']==2
    retained=db.execute(sa.text('SELECT source_record_sha256,source_observed_at FROM nba_player_gamelogs WHERE player_id=:p AND game_id=:g'),dict(p=participant,g=changed['game_id'])).one()
    # The existing writer already moves observation time for changes outside
    # the frozen core hash. Separate versions retain the earlier minutes proof.
    assert tuple(retained)==(rows[3]['source_record_sha256'],changed['source_observed_at'])
    write(db,[changed|{'source_observed_at':changed['source_observed_at']+timedelta(seconds=1)}])
    after=versions(db,participant,changed['game_id'])
    assert len(after)==2 and after[0]==before
    write(db,[rows[3]|{'source_observed_at':changed['source_observed_at']+timedelta(seconds=2)}])
    assert len(versions(db,participant,changed['game_id']))==3
    assert split(db,subject,candidate,first)==original


def test_missing_legacy_minutes_proof_is_withheld_and_partial_proof_is_unknown(db):
    rows,subject,participant,candidate=fixture_rows()
    pd.DataFrame(rows).to_sql('nba_player_gamelogs',db,if_exists='append',index=False)
    assert split(db,subject,candidate) is None
    store_participation(db,prepare_participation([rows[1]]))
    result=split(db,subject,candidate)
    assert result['active']['games']==1 and result['unknown_games']==2 and result['absent']['games']==0


def test_complete_official_removal_becomes_unknown_without_rewriting_old_receipts(db):
    rows,subject,participant,candidate=fixture_rows();write(db,rows,complete=True)
    first=db.execute(sa.text('SELECT clock_timestamp()')).scalar_one();original=split(db,subject,candidate,first)
    keep=[r|{'source_observed_at':r['source_observed_at']+timedelta(seconds=1)} for r in rows if r is not rows[3]]
    write(db,keep,complete=True)
    result=split(db,subject,candidate)
    assert result['active']['games']==1 and result['unknown_games']==1
    assert versions(db,participant,rows[3]['game_id'])[-1]['minutes'] is None
    assert split(db,subject,candidate,first)==original


def test_latest_identity_is_chosen_before_name_or_team_filters(db):
    rows,subject,participant,candidate=fixture_rows();write(db,rows)
    first=db.execute(sa.text('SELECT clock_timestamp()')).scalar_one()
    changed=[r|dict(player_name='Corrected identity',team_abbreviation='BOS',source_observed_at=r['source_observed_at']+timedelta(seconds=1)) for r in rows if r['player_id']==participant]
    write(db,changed)
    assert split(db,subject,candidate) is None
    assert split(db,subject,candidate,first)['active']['games']==2


def test_stale_changed_source_rolls_back_stat_and_minutes_together(db):
    rows,_,participant,_=fixture_rows();write(db,rows)
    original=versions(db,participant,rows[1]['game_id'])
    with pytest.raises(sa.exc.DBAPIError,match='Older NBA participation'):
        with db.begin_nested():write(db,[rows[1]|dict(minutes=0,source_observed_at=rows[1]['source_observed_at']-timedelta(seconds=1))])
    assert versions(db,participant,rows[1]['game_id'])==original
    assert db.execute(sa.text('SELECT minutes FROM nba_player_gamelogs WHERE player_id=:p AND game_id=:g'),dict(p=participant,g=rows[1]['game_id'])).scalar_one()==20


def test_numeric_roundtrip_and_forged_receipt_clock(db):
    rows,_,participant,_=fixture_rows();write(db,[rows[1]|{'minutes':20.15}])
    assert float(versions(db,participant,rows[1]['game_id'])[0]['minutes'])==20.2
    prepared=prepare_participation([rows[1]|dict(minutes=0,source_observed_at=rows[1]['source_observed_at']+timedelta(seconds=1))])[0]
    before=db.execute(sa.text('SELECT clock_timestamp()')).scalar_one()
    columns='player_id,player_name,game_id,game_date,season,team_abbreviation,minutes,source_provider,source_sha256,source_record_sha256,source_observed_at'
    db.execute(sa.text('INSERT INTO nba_participation_versions ('+columns+',recorded_at) VALUES ('+','.join(':'+c for c in columns.split(','))+",'2000-01-01')"),prepared)
    assert versions(db,participant,rows[1]['game_id'])[-1]['recorded_at']>=before


def test_access_repair_closes_browser_and_receipt_mutation_permissions():
    dsn=os.environ['SPORTSBET_TEST_DATABASE_URL'].replace('postgresql+psycopg://','postgresql://',1)
    with psycopg.connect(dsn) as conn:
        try:
            for role in ('anon','authenticated',READER,WORKER):
                if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():
                    conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
                conn.execute(sql.SQL('GRANT ALL ON nba_participation_versions TO {}').format(sql.Identifier(role)))
                conn.execute(sql.SQL('GRANT SELECT(minutes),INSERT(version_id,recorded_at),UPDATE(minutes) '
                    'ON nba_participation_versions TO {}').format(sql.Identifier(role)))
                conn.execute(sql.SQL('GRANT ALL ON SEQUENCE nba_participation_versions_version_id_seq TO {}').format(sql.Identifier(role)))
            conn.execute('ALTER TABLE nba_participation_versions DISABLE ROW LEVEL SECURITY')
            apply_access(conn)
            assert conn.execute("SELECT relrowsecurity FROM pg_class WHERE oid='nba_participation_versions'::regclass").fetchone()[0]
            for role in ('anon','authenticated',READER):
                assert not conn.execute("SELECT has_table_privilege(%s,'nba_participation_versions','SELECT,INSERT,UPDATE,DELETE,TRUNCATE')",(role,)).fetchone()[0]
                assert not conn.execute("SELECT has_sequence_privilege(%s,'nba_participation_versions_version_id_seq','USAGE,SELECT,UPDATE')",(role,)).fetchone()[0]
            assert conn.execute("SELECT has_column_privilege(%s,'nba_participation_versions','minutes','INSERT')",(WORKER,)).fetchone()[0]
            for column in ('version_id','recorded_at'):
                assert not conn.execute("SELECT has_column_privilege(%s,'nba_participation_versions',%s,'INSERT')",(WORKER,column)).fetchone()[0]
            for role in ('anon','authenticated',READER):
                assert not conn.execute("SELECT has_column_privilege(%s,'nba_participation_versions','minutes','SELECT')",(role,)).fetchone()[0]
            assert not conn.execute("SELECT has_column_privilege(%s,'nba_participation_versions','minutes','UPDATE')",(WORKER,)).fetchone()[0]
            conn.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(WORKER)))
            row=prepare_participation([source_row(game_id=uuid.uuid4().hex[:18])])[0]
            columns='player_id,player_name,game_id,game_date,season,team_abbreviation,minutes,source_provider,source_sha256,source_record_sha256,source_observed_at'
            values=tuple(row[c] for c in columns.split(','))
            version=conn.execute('INSERT INTO nba_participation_versions ('+columns+') VALUES ('+','.join(['%s']*len(values))+') RETURNING version_id,recorded_at',values).fetchone()
            assert version[0]>0 and version[1]>=row['source_observed_at']
            for statement in ('UPDATE nba_participation_versions SET minutes=0','DELETE FROM nba_participation_versions','TRUNCATE nba_participation_versions',
                'INSERT INTO nba_participation_versions(recorded_at) VALUES(now())','SELECT capture_nba_participation_version()'):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    with conn.transaction():conn.execute(statement)
        finally:conn.rollback()


def test_upgrade_after_roles_does_not_backfill_legacy_minutes(db):
    migration=runpy.run_path('alembic/versions/0048_nba_participation_versions.py')
    with Operations.context(MigrationContext.configure(db)):migration['downgrade']()
    rows,_,_,_=fixture_rows()
    pd.DataFrame(rows).to_sql('nba_player_gamelogs',db,if_exists='append',index=False)
    before=db.execute(sa.text('SELECT * FROM nba_player_gamelogs ORDER BY player_id,game_id')).mappings().all()
    for role in ('anon','authenticated',WORKER,READER):
        if not db.execute(sa.text('SELECT 1 FROM pg_roles WHERE rolname=:r'),{'r':role}).first():
            db.execute(sa.text('CREATE ROLE '+role+' NOLOGIN'))
    db.execute(sa.text('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon'))
    db.execute(sa.text('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon'))
    with Operations.context(MigrationContext.configure(db)):migration['upgrade']()
    assert db.execute(sa.text('SELECT count(*) FROM nba_participation_versions')).scalar_one()==0
    assert db.execute(sa.text('SELECT * FROM nba_player_gamelogs ORDER BY player_id,game_id')).mappings().all()==before
    assert not db.execute(sa.text("SELECT has_table_privilege('anon','nba_participation_versions','SELECT,INSERT,UPDATE,DELETE')")).scalar_one()
    assert not db.execute(sa.text("SELECT has_sequence_privilege('anon','nba_participation_versions_version_id_seq','USAGE,SELECT,UPDATE')")).scalar_one()
    assert db.execute(sa.text("SELECT has_column_privilege('sportsbet_worker','nba_participation_versions','minutes','INSERT')")).scalar_one()
    assert not db.execute(sa.text("SELECT has_column_privilege('sportsbet_worker','nba_participation_versions','recorded_at','INSERT')")).scalar_one()
    with Operations.context(MigrationContext.configure(db)):migration['downgrade']()


def test_populated_downgrade_refuses_to_erase_participation_receipts(db):
    migration=runpy.run_path('alembic/versions/0048_nba_participation_versions.py')
    rows,_,_,_=fixture_rows();write(db,rows)
    before=db.execute(sa.text('SELECT * FROM nba_participation_versions ORDER BY version_id')).mappings().all()
    with pytest.raises(sa.exc.DBAPIError,match='Retained NBA participation'):
        with db.begin_nested(),Operations.context(MigrationContext.configure(db)):migration['downgrade']()
    assert db.execute(sa.text('SELECT * FROM nba_participation_versions ORDER BY version_id')).mappings().all()==before


@pytest.mark.parametrize('relationship',['teammate','opponent'])
def test_correct_team_relation_and_missing_minutes_are_source_replayed(db,relationship):
    rows,subject,participant,candidate=fixture_rows()
    if relationship=='opponent':
        candidate=candidate|dict(relationship='opponent',unit='defense')
        rows=[source_row(**(r|dict(team_abbreviation='BOS',opponent_team='LAC'))) if r['player_id']==subject else r for r in rows]
    write(db,rows)
    result=split(db,subject,candidate)
    assert result['active']['games']==2 and result['absent']['games']==1
    damaged=rows[3]|dict(minutes=None,source_observed_at=rows[3]['source_observed_at']+timedelta(seconds=1))
    write(db,[damaged])
    result=split(db,subject,candidate)
    assert result['active']['games']==1 and result['unknown_games']==1


def test_official_ingester_commits_provider_minutes_and_rolls_back_both_writes(db,monkeypatch):
    from sportsbet.ingestion import nba_gamelogs
    from tests.test_nba_gamelogs_ingest import _make_sample_df
    response=MagicMock();response.get_data_frames.return_value=[_make_sample_df()]
    monkeypatch.setattr(nba_gamelogs,'PlayerGameLogs',lambda **kwargs:response)
    monkeypatch.setattr(nba_gamelogs.time,'sleep',lambda seconds:None)
    class BoundEngine:
        @contextmanager
        def begin(self):
            with db.begin_nested():yield db
    assert nba_gamelogs.ingest_nba_gamelogs_season(2023,BoundEngine())==3
    first=versions(db,2544,'0022300001')
    assert len(first)==1 and first[0]['minutes']==35
    updated=_make_sample_df();updated.loc[0,'MIN']=0
    response.get_data_frames.return_value=[updated]
    assert nba_gamelogs.ingest_nba_gamelogs_season(2023,BoundEngine())==3
    assert len(versions(db,2544,'0022300001'))==2
    original_stats=db.execute(sa.text("SELECT * FROM nba_player_gamelogs WHERE player_id=2544 AND game_id='0022300001'")).mappings().one()
    original_proofs=versions(db,2544,'0022300001')
    updated.loc[0,'PTS']=99;response.get_data_frames.return_value=[updated]
    def unavailable(*args,**kwargs):raise RuntimeError('Participation write failed')
    monkeypatch.setattr(nba_gamelogs,'store_participation',unavailable)
    with pytest.raises(RuntimeError,match='Participation write failed'):
        nba_gamelogs.ingest_nba_gamelogs_season(2023,BoundEngine())
    assert db.execute(sa.text("SELECT * FROM nba_player_gamelogs WHERE player_id=2544 AND game_id='0022300001'")).mappings().one()==original_stats
    assert versions(db,2544,'0022300001')==original_proofs


def test_official_ingester_still_writes_missing_participation_after_stat_noop(db,monkeypatch):
    from sportsbet.ingestion import nba_gamelogs
    from tests.test_nba_gamelogs_ingest import _make_sample_df
    response=MagicMock();response.get_data_frames.return_value=[_make_sample_df()]
    monkeypatch.setattr(nba_gamelogs,'PlayerGameLogs',lambda **kwargs:response)
    monkeypatch.setattr(nba_gamelogs.time,'sleep',lambda seconds:None)
    original_store=nba_gamelogs.store_participation;calls=[]
    def delayed_participation(conn,rows,**kwargs):
        calls.append(len(rows))
        if len(calls)>1:original_store(conn,rows,**kwargs)
    monkeypatch.setattr(nba_gamelogs,'store_participation',delayed_participation)
    class BoundEngine:
        @contextmanager
        def begin(self):
            with db.begin_nested():yield db
    assert nba_gamelogs.ingest_nba_gamelogs_season(2023,BoundEngine())==3
    assert versions(db,2544,'0022300001')==[]
    before=db.execute(sa.text("SELECT ctid::text,to_jsonb(n) FROM nba_player_gamelogs n "
        "WHERE player_id=2544 AND game_id='0022300001'")).one()

    assert nba_gamelogs.ingest_nba_gamelogs_season(2023,BoundEngine())==3

    assert calls==[3,3]
    assert db.execute(sa.text("SELECT ctid::text,to_jsonb(n) FROM nba_player_gamelogs n "
        "WHERE player_id=2544 AND game_id='0022300001'")).one()==before
    assert len(versions(db,2544,'0022300001'))==1


def test_recent_nba_context_uses_actual_source_proofs_with_old_history_kept_separate(db):
    rows,subject,participant,candidate=fixture_rows()
    prepared=[]
    for row in rows:
        if row['game_date'].day==1:prepared.append(row)
        else:prepared.append(source_row(**(row|dict(game_date=date(2026,9,row['game_date'].day),season=2026))))
    write(db,prepared)
    result=split(db,subject,candidate)
    assert result['active']==dict(games=2,mean=20.,hit_rate=.5)
    recent=result['recent_window']
    assert recent['active']==dict(games=1,mean=30.,hit_rate=1.)
    assert recent['absent']==dict(games=1,mean=25.,hit_rate=1.)
    assert recent['unknown_games']==0 and recent['sample_window']['active']['newest']=='2026-09-02'


@pytest.mark.skipif(not os.environ.get('SPORTSBET_TEST_DATABASE_URL'),
    reason='Disposable PostgreSQL required')
def test_opted_in_writer_repairs_missing_observation_and_default_still_updates():
    engine=sa.create_engine(os.environ['SPORTSBET_TEST_DATABASE_URL'])
    table=sa.Table('noop_writer_'+uuid.uuid4().hex[:12],sa.MetaData(),
        sa.Column('id',sa.Integer,primary_key=True),sa.Column('value',sa.Integer),
        sa.Column('source_provider',sa.Text),sa.Column('source_sha256',sa.Text),
        sa.Column('source_record_sha256',sa.Text),
        sa.Column('source_observed_at',sa.DateTime(timezone=True)))
    observed=datetime.now(timezone.utc)-timedelta(minutes=1)
    row=dict(id=1,value=None,source_provider='fixture',source_sha256='a'*64,
        source_record_sha256='b'*64,source_observed_at=observed)
    opted=upsert_rows(['id'],preserve_observation_on_unchanged=True,skip_unchanged_updates=True)
    default=upsert_rows(['id'],preserve_observation_on_unchanged=True)
    try:
        with engine.connect() as conn:
            transaction=conn.begin()
            try:
                table.create(conn)
                conn.execute(table.insert(),row|dict(source_observed_at=None))
                assert pd.DataFrame([row]).to_sql(table.name,conn,if_exists='append',
                    index=False,method=opted)==1
                assert conn.execute(sa.select(table.c.source_observed_at)).scalar_one()==observed
                before=conn.execute(sa.text('SELECT ctid::text FROM '+table.name)).scalar_one()
                repeated=row|dict(source_sha256='c'*64,source_observed_at=observed+timedelta(seconds=1))
                assert pd.DataFrame([repeated]).to_sql(table.name,conn,if_exists='append',
                    index=False,method=opted)==0
                assert conn.execute(sa.text('SELECT ctid::text FROM '+table.name)).scalar_one()==before
                assert pd.DataFrame([repeated]).to_sql(table.name,conn,if_exists='append',
                    index=False,method=default)==1
                assert conn.execute(sa.text('SELECT ctid::text FROM '+table.name)).scalar_one()!=before
                assert conn.execute(sa.select(table.c.source_sha256,
                    table.c.source_observed_at)).one()==('a'*64,observed)
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
