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
