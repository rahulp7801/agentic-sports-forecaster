import json
import os
from datetime import datetime, timezone

import pytest

from sportsbet.ingestion.provenance import stat_row_sha256
from sportsbet.quant.cfb_history_completeness import load_primary
from sportsbet.ingestion.cfb_final_evidence import inspect_bundle
from sportsbet.quant.cfb_history_supplements import plan_supplements, apply_bundle
from tests.test_cfb_final_evidence import bundle, NOW, PLAYER, EVENT
from tests.test_cfb_history_completeness import primary

pytestmark = pytest.mark.skipif(not os.environ.get('SPORTSBET_TEST_DATABASE_URL'),reason='Disposable PostgreSQL required')


def test_atomic_supplement_view_replay_and_source_refresh_invalidation():
    import psycopg
    url=os.environ['SPORTSBET_TEST_DATABASE_URL'].replace('postgresql+psycopg://','postgresql://',1)
    raw=json.dumps(bundle()); evidence=inspect_bundle(bundle(),now=NOW)
    with psycopg.connect(url) as conn:
        try:
            row=primary(); row['game_id']=str(row['game_id'])
            conn.execute('INSERT INTO public.cfb_player_gamelogs ('+','.join(row)+') VALUES ('
                +','.join(['%s']*len(row))+')',tuple(row.values()))
            class Session:
                def execute(self,sql,args=()):return conn.execute(sql.replace('?', '%s'),args)
            rows=load_primary(Session(),evidence,cutoff=NOW.date().isoformat(),season_min=2004)
            plan=plan_supplements(raw,rows,now=NOW)
            with pytest.raises(ValueError,match='re-preview'):
                apply_bundle(conn,raw,expected_count=1,expected_plan_sha256='wrong',now=NOW)
            assert conn.execute('SELECT count(*) FROM public.cfb_receiving_supplements').fetchone()[0]==0
            assert apply_bundle(conn,raw,expected_count=1,expected_plan_sha256=plan['plan_sha256'],now=NOW)==1
            original=conn.execute('SELECT receiving_yards,receptions,rushing_yards,source_record_sha256 '
                'FROM public.cfb_player_gamelogs WHERE athlete_id=%s AND game_id=%s',(int(PLAYER),EVENT)).fetchone()
            assert original==(None,None,68,row['source_record_sha256'])
            def effective():
                return conn.execute('SELECT receiving_yards,receptions,rushing_yards,source_record_sha256,history_policy_version '
                    'FROM public.cfb_effective_gamelogs WHERE athlete_id=%s AND game_id=%s',(int(PLAYER),EVENT)).fetchone()
            assert effective()==(0,0,68,plan['updates'][0]['effective_record_sha256'],'cfb-explicit-receiving-v1')
            # Dashboard and model read the same explicit zero; raw row stays NULL.
            public=conn.execute("SELECT payload FROM public.dashboard_gamelogs WHERE sport='cfb' AND player_id=%s AND game_key=%s",
                (PLAYER,EVENT)).fetchone()[0]
            assert public['rec_yds']==public['receptions']==0
            from sportsbet.graph.models import PropParams
            from sportsbet.prop.query_builder import PropQueryBuilder
            from sportsbet.settlement import _actual
            from sportsbet.ingestion.cfb_supplement_proof import valid_supplement
            from datetime import date,timedelta
            from decimal import Decimal
            import re
            inserted=conn.execute('SELECT inserted_at FROM public.cfb_receiving_supplements WHERE athlete_id=%s AND game_id=%s',
                (int(PLAYER),EVENT)).fetchone()[0]
            available=max(inserted,datetime.fromisoformat(plan['updates'][0]['observed_at']))
            def sample(cutoff):
                params=PropParams(game_id='future',player_id=PLAYER,season=2024,sport='cfb',
                    prop_type='rec_yds',line=Decimal('0.5'),filters={},as_of_date=date(2026,9,30),
                    observed_before=cutoff,last_n_games=40)
                query,args=PropQueryBuilder.build(params);ordered=[]
                def bind(match):
                    ordered.append(args[int(match[1])-1]);return '%s'
                return conn.execute(re.sub(r'\$(\d+)',bind,query),ordered).fetchone()
            assert sample(available-timedelta(microseconds=1))[0]==0
            assert sample(available)==(1,0,0,0)
            game=dict(provider_event_id=EVENT,game_time='2026-09-26T16:00:00Z',
                home_abbreviation='IU',away_abbreviation='NU',home_name='Indiana Hoosiers',away_name='Northwestern Wildcats')
            value,proof=_actual(Session(),dict(player_id=PLAYER,prop_type='rec_yds'),'cfb','2026-09-26',game)
            assert value==0 and proof['provider']=='sportsdataverse_espn_supplement'
            assert valid_supplement(proof['record'],proof['supplement_manifest'],proof['sha256'],proof['observed_at'],game['game_time'])

            with pytest.raises(ValueError,match='re-preview'):
                apply_bundle(conn,raw,expected_count=1,expected_plan_sha256=plan['plan_sha256'],now=NOW)
            # Same normalized record in a refreshed release keeps its supplement.
            conn.execute('UPDATE public.cfb_player_gamelogs SET source_sha256=%s WHERE athlete_id=%s AND game_id=%s',
                ('f'*64,int(PLAYER),EVENT))
            assert effective()[0:3]==(0,0,68)
            # A changed value invalidates even a dishonest unchanged record digest.
            conn.execute('UPDATE public.cfb_player_gamelogs SET rushing_yards=69 WHERE athlete_id=%s AND game_id=%s',(int(PLAYER),EVENT))
            assert effective()[0:3]==(None,None,69)
            assert effective()[-1]=='primary-v1'
            assert conn.execute('SELECT count(*) FROM public.cfb_receiving_supplements').fetchone()[0]==1
        finally:
            conn.rollback()
