"""Database guard for CFB source refresh chronology."""
import os
from datetime import datetime, timedelta, timezone
import uuid

import pandas as pd
import pytest
import sqlalchemy as sa

from sportsbet.ingestion.provenance import stat_row_sha256
from sportsbet.ingestion.upsert import upsert_rows
from tests.test_cfb_history_completeness import primary

pytestmark = pytest.mark.skipif(not os.environ.get('SPORTSBET_TEST_DATABASE_URL'),
    reason='Disposable PostgreSQL required')


def test_identical_cfb_refresh_retains_first_observation_and_correction_archives_old_row():
    import psycopg
    url=os.environ['SPORTSBET_TEST_DATABASE_URL'].replace('postgresql+psycopg://','postgresql://',1)
    row=primary();row['game_id']=str(row['game_id'])
    identity=(row['athlete_id'],row['game_id'])
    with psycopg.connect(url) as conn:
        try:
            conn.execute('INSERT INTO public.cfb_player_gamelogs ('+','.join(row)+') VALUES ('
                +','.join(['%s']*len(row))+')',tuple(row.values()))
            original=conn.execute('SELECT source_observed_at,source_sha256,rushing_yards '
                'FROM public.cfb_player_gamelogs WHERE athlete_id=%s AND game_id=%s',identity).fetchone()
            later=conn.execute('SELECT clock_timestamp()').fetchone()[0]
            repeat=conn.execute('UPDATE public.cfb_player_gamelogs SET source_observed_at=%s, '
                'source_sha256=%s WHERE athlete_id=%s AND game_id=%s',
                (later,'f'*64,*identity))
            assert repeat.rowcount==0
            assert conn.execute('SELECT source_observed_at,source_sha256,rushing_yards '
                'FROM public.cfb_player_gamelogs WHERE athlete_id=%s AND game_id=%s',identity).fetchone()==original
            assert conn.execute('SELECT count(*) FROM public.cfb_primary_revisions '
                'WHERE athlete_id=%s AND game_id=%s',identity).fetchone()[0]==0

            corrected=primary(rushing_yards=69)
            change=conn.execute('UPDATE public.cfb_player_gamelogs SET rushing_yards=%s, '
                'source_record_sha256=%s,source_observed_at=%s '
                'WHERE athlete_id=%s AND game_id=%s',
                (69,corrected['source_record_sha256'],later,*identity))
            assert change.rowcount==1
            current=conn.execute('SELECT rushing_yards,source_record_sha256,source_observed_at '
                'FROM public.cfb_player_gamelogs WHERE athlete_id=%s AND game_id=%s',identity).fetchone()
            assert current[0:2]==(69,corrected['source_record_sha256'])
            assert current[2]>=later and current[2]>original[0]
            archived=conn.execute('SELECT source_record_sha256,source_observed_at,replaced_at,row_data '
                'FROM public.cfb_primary_revisions WHERE athlete_id=%s AND game_id=%s',identity).fetchone()
            assert archived[0]==row['source_record_sha256'] and archived[1]==original[0]
            assert archived[2]>=later and archived[3]['rushing_yards']==68
            assert archived[3]['source_sha256']==original[1]
            assert conn.execute('SELECT count(*) FROM public.cfb_primary_revisions '
                'WHERE athlete_id=%s AND game_id=%s',identity).fetchone()[0]==1
            for role in ('anon','authenticated','sportsbet_dashboard'):
                if conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():
                    assert not conn.execute('SELECT has_table_privilege(%s,%s,%s)',
                        (role,'public.cfb_primary_revisions','SELECT')).fetchone()[0]
        finally:
            conn.rollback()


def test_opted_in_cfb_replay_skips_update_trigger_but_correction_retains_revision():
    engine=sa.create_engine(os.environ['SPORTSBET_TEST_DATABASE_URL'])
    game=int(uuid.uuid4().int%900000000)+100000000
    observed=datetime.now(timezone.utc)-timedelta(minutes=5)
    row=primary(game_id=game,source_observed_at=observed)
    identity=dict(a=row['athlete_id'],g=str(game))
    writer=upsert_rows(['athlete_id','game_id'],preserve_observation_on_unchanged=True,
        skip_unchanged_updates=True)
    try:
        with engine.connect() as conn:
            transaction=conn.begin()
            try:
                conn.execute(sa.text('CREATE TEMP TABLE cfb_noop_update_calls (calls integer NOT NULL)'))
                conn.execute(sa.text('INSERT INTO cfb_noop_update_calls VALUES (0)'))
                conn.execute(sa.text('''CREATE FUNCTION pg_temp.count_cfb_noop_update() RETURNS trigger
                    LANGUAGE plpgsql AS $$ BEGIN
                      UPDATE pg_temp.cfb_noop_update_calls SET calls=calls+1;
                      RETURN NEW;
                    END $$'''))
                # Trigger names execute in lexical order: count before the existing
                # archive trigger can return NULL for a logically unchanged row.
                conn.execute(sa.text('''CREATE TRIGGER aa_test_cfb_noop_update
                    BEFORE UPDATE ON public.cfb_player_gamelogs FOR EACH ROW
                    EXECUTE FUNCTION pg_temp.count_cfb_noop_update()'''))
                assert pd.DataFrame([row]).to_sql('cfb_player_gamelogs',conn,if_exists='append',
                    index=False,method=writer)==1
                before=conn.execute(sa.text('SELECT ctid::text,xmin::text,to_jsonb(c) '
                    'FROM cfb_player_gamelogs c WHERE athlete_id=:a AND game_id=:g'),identity).one()
                repeated=primary(game_id=game,source_player_sha256='e'*64,
                    source_schedule_sha256='f'*64,source_observed_at=observed+timedelta(seconds=1))

                assert pd.DataFrame([repeated]).to_sql('cfb_player_gamelogs',conn,if_exists='append',
                    index=False,method=writer)==0

                assert conn.execute(sa.text('SELECT calls FROM cfb_noop_update_calls')).scalar_one()==0
                assert conn.execute(sa.text('SELECT ctid::text,xmin::text,to_jsonb(c) '
                    'FROM cfb_player_gamelogs c WHERE athlete_id=:a AND game_id=:g'),identity).one()==before
                assert conn.execute(sa.text('SELECT count(*) FROM cfb_primary_revisions '
                    'WHERE athlete_id=:a AND game_id=:g'),identity).scalar_one()==0
                corrected=repeated|dict(rushing_yards=69)
                corrected['source_record_sha256']=stat_row_sha256('cfb',corrected)
                assert pd.DataFrame([corrected]).to_sql('cfb_player_gamelogs',conn,if_exists='append',
                    index=False,method=writer)==1
                assert conn.execute(sa.text('SELECT calls FROM cfb_noop_update_calls')).scalar_one()==1
                current=conn.execute(sa.text('SELECT ctid::text,rushing_yards,source_observed_at '
                    'FROM cfb_player_gamelogs WHERE athlete_id=:a AND game_id=:g'),identity).one()
                assert current[0]!=before[0] and current[1]==69
                assert current[2]>observed and current[2]>=corrected['source_observed_at']
                old=conn.execute(sa.text('SELECT row_data FROM cfb_primary_revisions '
                    'WHERE athlete_id=:a AND game_id=:g'),identity).scalar_one()
                assert old['source_record_sha256']==row['source_record_sha256']
                assert old['source_sha256']==row['source_sha256'] and old['rushing_yards']==68
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
