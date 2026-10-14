"""Database guard for CFB source refresh chronology."""
import os

import pytest

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