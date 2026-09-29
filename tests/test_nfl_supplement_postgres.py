import json
import os

import pytest

from sportsbet.ingestion.nfl_final_evidence import inspect_bundle
from sportsbet.quant.nfl_history_supplements import plan_supplements, apply_bundle, load_state
from tests.test_nfl_final_evidence import bundle, NOW
from tests.test_nfl_history_supplements import game, primary

pytestmark = pytest.mark.skipif(not os.environ.get('SPORTSBET_TEST_DATABASE_URL'), reason='Disposable PostgreSQL required')


def test_reviewed_nfl_archive_is_atomic_replay_safe_and_private():
    import psycopg
    from psycopg.types.json import Jsonb
    url = os.environ['SPORTSBET_TEST_DATABASE_URL'].replace('postgresql+psycopg://','postgresql://',1)
    raw = json.dumps(bundle()); evidence = inspect_bundle(bundle(),now=NOW)
    with psycopg.connect(url) as conn:
        try:
            g = game()
            conn.execute('INSERT INTO public.games ('+','.join(g)+') VALUES ('+','.join(['%s']*len(g))+')', tuple(g.values()))
            class Session:
                def execute(self,sql,args=()): return conn.execute(sql.replace('?', '%s'),args)
            plan = plan_supplements(raw, *load_state(Session(), evidence), now=NOW)
            conn.execute('SET LOCAL ROLE sportsbet_worker')
            with pytest.raises(ValueError,match='re-preview'):
                apply_bundle(conn,raw,expected_count=1,expected_plan_sha256='wrong',now=NOW)
            assert conn.execute('SELECT count(*) FROM public.nfl_history_source_bundles').fetchone()[0] == 0
            assert apply_bundle(conn,raw,expected_count=1,expected_plan_sha256=plan['plan_sha256'],now=NOW) == 1
            assert conn.execute('SELECT response_text FROM public.nfl_history_source_bundles').fetchone()[0] == raw
            conn.execute('RESET ROLE')
            item, = plan['updates']
            assert conn.execute('SELECT stat_row FROM public.nfl_receiving_supplements').fetchone()[0] == item['stat_row']
            assert conn.execute('SELECT count(*) FROM public.player_stats WHERE player_id=%s',(item['player_id'],)).fetchone()[0] == 0
            with pytest.raises(ValueError,match='re-preview'):
                apply_bundle(conn,raw,expected_count=1,expected_plan_sha256=plan['plan_sha256'],now=NOW)
            for table in ('nfl_history_source_bundles','nfl_receiving_supplements'):
                assert conn.execute("SELECT has_table_privilege('sportsbet_worker',%s,'SELECT') AND has_table_privilege('sportsbet_worker',%s,'INSERT')",
                    ('public.'+table,)*2).fetchone()[0]
                for role in ('sportsbet_worker','sportsbet_dashboard'):
                    assert not conn.execute('SELECT has_table_privilege(%s,%s,%s)',
                        (role,'public.'+table,'UPDATE,DELETE,TRUNCATE' if role=='sportsbet_worker' else 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')).fetchone()[0]
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    conn.execute('SET LOCAL ROLE sportsbet_worker')
                    conn.execute('DELETE FROM public.nfl_receiving_supplements')
            for bad in (item['stat_row'] | dict(receptions=None), item['stat_row'] | dict(rushing_yards=0),
                        item['stat_row'] | dict(player_id='00-0000000'), item['stat_row'] | dict(receiving_yards=1)):
                with pytest.raises(psycopg.errors.CheckViolation):
                    with conn.transaction():
                        conn.execute('UPDATE public.nfl_receiving_supplements SET stat_row=%s',(Jsonb(bad),))
            row = primary(rushing_yards=3)
            conn.execute('INSERT INTO public.player_stats ('+','.join(row)+') VALUES ('+','.join(['%s']*len(row))+')',tuple(row.values()))
            replay = plan_supplements(raw,*load_state(Session(),evidence),now=NOW)
            assert replay['updates'] == [] and replay['complete'] == replay['retained'] == 1
            assert conn.execute('SELECT rushing_yards FROM public.player_stats WHERE player_id=%s',(item['player_id'],)).fetchone()[0] == 3
        finally:
            conn.rollback()
