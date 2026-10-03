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
    from sportsbet.db.access import provision_roles, READER, WORKER
    import secrets
    url = os.environ['SPORTSBET_TEST_DATABASE_URL'].replace('postgresql+psycopg://','postgresql://',1)
    raw = json.dumps(bundle()); evidence = inspect_bundle(bundle(),now=NOW)
    with psycopg.connect(url) as conn:
        try:
            provision_roles(conn, {role: secrets.token_urlsafe(32) for role in (READER, WORKER)})
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
            from datetime import date,datetime,timedelta
            from decimal import Decimal
            import re
            from sportsbet.graph.models import PropParams
            from sportsbet.prop.query_builder import PropQueryBuilder
            from sportsbet.model_contract import NFL_HISTORY_FROZEN_AT
            from sportsbet.settlement import _actual
            from sportsbet.ingestion.nfl_supplement_proof import valid_supplement
            inserted=conn.execute('SELECT inserted_at FROM public.nfl_receiving_supplements').fetchone()[0]
            available=max(inserted,datetime.fromisoformat(NFL_HISTORY_FROZEN_AT),datetime.fromisoformat(item['observed_at']))
            def sample(cutoff):
                params=PropParams(sport='nfl',player_id=item['player_id'],season=2024,game_id='future',
                    prop_type='rec_yds',line=Decimal('0.5'),filters={},as_of_date=date(2026,9,30),
                    observed_before=cutoff,last_n_games=40)
                query,args=PropQueryBuilder.build(params);ordered=[]
                def bind(match):ordered.append(args[int(match[1])-1]);return '%s'
                return conn.execute(re.sub(r'\$(\d+)',bind,query),ordered).fetchone()
            assert sample(available)==(1,0,0,0)
            import asyncio
            from sportsbet.prop.injury_context import _nfl_split
            snap=bundle()['participation'][0]
            snap_row=snap['row']|{k:snap[k] for k in ('source_provider','source_sha256','source_record_sha256','source_observed_at')}
            conn.execute('INSERT INTO public.nfl_snap_counts ('+','.join(snap_row)+') VALUES ('+','.join(['%s']*len(snap_row))+')',tuple(snap_row.values()))
            class ContextConnection:
                async def fetchrow(self,query,*args):
                    ordered=[]
                    def bind(match):ordered.append(args[int(match[1])-1]);return '%s'
                    cur=conn.execute(re.sub(r'\$(\d+)',bind,query),ordered)
                    return dict(zip([c.name for c in cur.description],cur.fetchone(),strict=True))
            candidate=dict(stat_team='DEN',participant_id=snap_row['pfr_player_id'],unit='offense',
                relationship='teammate',player='Context fixture',status='Questionable',position='TE',team='DEN')
            context=asyncio.run(_nfl_split(ContextConnection(),item['player_id'],2024,date(2026,9,30),'rec_yds',.5,'under',candidate,available))
            assert context['active']['games']==1 and context['active']['mean']==0 and context['active']['hit_rate']==1
            assert asyncio.run(_nfl_split(ContextConnection(),item['player_id'],2024,date(2026,9,30),'rec_yds',.5,'under',candidate,inserted-timedelta(microseconds=1))) is None

            assert sample(inserted-timedelta(microseconds=1))[0]==0
            public=conn.execute("SELECT payload FROM public.dashboard_gamelogs WHERE sport='nfl' AND player_id=%s AND game_key=%s",(item['player_id'],g['game_id'])).fetchone()[0]
            assert public['rec_yds']==public['receptions']==0
            assert public['pass_yds'] is public['rush_yds'] is None
            asof=conn.execute("SELECT record_available_at,payload FROM public.dashboard_gamelogs_asof "
                "WHERE sport='nfl' AND player_id=%s AND game_key=%s",(item['player_id'],g['game_id'])).fetchone()
            assert asof[0]==max(inserted,datetime.fromisoformat(item['observed_at']))
            assert asof[1]==public
            assert conn.execute("SELECT count(*) FROM public.dashboard_gamelogs_asof WHERE sport='nfl' "
                "AND player_id=%s AND game_key=%s AND record_available_at<=%s",
                (item['player_id'],g['game_id'],asof[0]-timedelta(microseconds=1))).fetchone()[0]==0
            assert conn.execute("SELECT count(*) FROM public.dashboard_gamelogs_asof WHERE sport='nfl' "
                "AND player_id=%s AND game_key=%s AND record_available_at<=%s",
                (item['player_id'],g['game_id'],asof[0])).fetchone()[0]==1
            final=item['manifest']['game']
            value,proof=_actual(Session(),dict(player_id=item['player_id'],prop_type='rec_yds',model_version='empirical-jeffreys-v4-nfl-history-v1'),'nfl',final['date'],final)
            assert value==0 and proof['provider']=='nflverse_espn_supplement'
            assert valid_supplement(proof['record'],proof['supplement_manifest'],proof['sha256'],proof['observed_at'],final)
            conn.execute('UPDATE public.games SET game_date=%s WHERE game_id=%s',('2026-09-21',g['game_id']))
            assert sample(available)[0]==0
            conn.execute('UPDATE public.games SET game_date=%s WHERE game_id=%s',(g['game_date'],g['game_id']))

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
            row = primary(rushing_yards=3, player_name='Adam Trautman')
            conn.execute('INSERT INTO public.player_stats ('+','.join(row)+') VALUES ('+','.join(['%s']*len(row))+')',tuple(row.values()))
            replay = plan_supplements(raw,*load_state(Session(),evidence),now=NOW)
            assert replay['updates'] == [] and replay['complete'] == replay['retained'] == 1
            assert conn.execute('SELECT rushing_yards FROM public.player_stats WHERE player_id=%s',(item['player_id'],)).fetchone()[0] == 3
            assert sample(available)[0]==1  # Primary arrival replaces, never duplicates, the archived game.
            conn.execute('UPDATE public.player_stats SET receptions=1 WHERE player_id=%s',(item['player_id'],))
            assert sample(available)[0]==0  # Conflicting receiving sources block the player's effective history.
            assert conn.execute('SELECT count(*) FROM public.nfl_receiving_supplements').fetchone()[0]==1
            assert conn.execute("SELECT count(*) FROM public.dashboard_gamelog_versions "
                "WHERE sport='nfl' AND player_id=%s AND game_key=%s",
                (item['player_id'],g['game_id'])).fetchone()[0]==0
            core=conn.execute("""SELECT payload,record_available_at
                FROM public.dashboard_nfl_core_gamelogs_asof
                WHERE player_id=%s AND game_key=%s
                ORDER BY record_available_at DESC LIMIT 1""",
                (item['player_id'],g['game_id'])).fetchone()
            assert core is not None and core[0]['rush_yds']==3
            assert core[0]['rec_yds'] is None and core[0]['receptions'] is None
            assert conn.execute("""SELECT count(*) FROM public.dashboard_nfl_core_gamelogs_asof
                WHERE player_id=%s AND game_key=%s AND record_available_at<=%s""",
                (item['player_id'],g['game_id'],core[1])).fetchone()[0]==2
            assert conn.execute("SELECT has_table_privilege('sportsbet_dashboard',"
                "'public.dashboard_nfl_core_gamelogs_asof','SELECT')").fetchone()[0]

            # The later matching primary must not erase a verified supplement
            # that an earlier forecast could have read.
            late=inserted+timedelta(hours=1)
            conn.execute('UPDATE public.player_stats SET receptions=0,player_name=%s,'
                'source_observed_at=%s WHERE player_id=%s',
                ('Adam Trautman',late,item['player_id']))
            def displayed(cutoff):
                return conn.execute("""SELECT payload FROM (
                    SELECT DISTINCT ON (sport,COALESCE(player_id,player_name),game_key)
                        payload,game_date,player_name,game_key
                    FROM public.dashboard_gamelog_versions
                    WHERE sport='nfl' AND player_id=%s AND game_key=%s
                      AND record_available_at<=%s::timestamptz
                    ORDER BY sport,COALESCE(player_id,player_name),game_key,
                        record_available_at DESC NULLS LAST
                    ) latest ORDER BY game_date DESC,player_name,game_key LIMIT 20""",
                    (item['player_id'],g['game_id'],cutoff)).fetchall()
            assert len(displayed(available-timedelta(microseconds=1)))==0
            earlier=displayed(available)
            assert len(earlier)==1 and earlier[0][0]['receptions']==0
            assert earlier[0][0]['rush_yds'] is None
            current=displayed(late)
            assert len(current)==1 and current[0][0]['rush_yds']==3
            assert conn.execute("SELECT count(*) FROM public.dashboard_gamelog_versions "
                "WHERE sport='nfl' AND player_id=%s AND game_key=%s",
                (item['player_id'],g['game_id'])).fetchone()[0]==2
            for role in ('anon','authenticated','sportsbet_worker'):
                if conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():
                    assert not conn.execute('SELECT has_table_privilege(%s,%s,%s)',
                        (role,'public.dashboard_gamelog_versions','SELECT')).fetchone()[0]
            # Some disposable suites provision the reader after migrations.
            # When the baseline as-of view is granted, this view must be too.
            baseline=conn.execute('SELECT has_table_privilege(%s,%s,%s)',
                ('sportsbet_dashboard','public.dashboard_gamelogs_asof','SELECT')).fetchone()[0]
            versions=conn.execute('SELECT has_table_privilege(%s,%s,%s)',
                ('sportsbet_dashboard','public.dashboard_gamelog_versions','SELECT')).fetchone()[0]
            assert versions==baseline

        finally:
            conn.rollback()
