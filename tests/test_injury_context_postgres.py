"""Execute historical-context chronology checks on disposable PostgreSQL."""
import asyncio
from datetime import date,datetime,timedelta,timezone
import os
import re
import uuid

import pytest

from sportsbet.prop.injury_context import _nfl_split,_nba_split

pytestmark=pytest.mark.skipif(not os.environ.get('SPORTSBET_TEST_DATABASE_URL'),reason='Disposable PostgreSQL required')
NOW=datetime(2026,9,29,tzinfo=timezone.utc)
LATE=NOW+timedelta(seconds=1)


class ContextConnection:
    def __init__(self,conn):self.conn=conn
    def query(self,sql,args):
        ordered=[]
        def bind(match):ordered.append(args[int(match[1])-1]);return '%s'
        return self.conn.execute(re.sub(r'\$(\d+)',bind,sql),ordered)
    async def fetch(self,sql,*args):
        cur=self.query(sql,args);names=[c.name for c in cur.description]
        return [dict(zip(names,row,strict=True)) for row in cur.fetchall()]
    async def fetchrow(self,sql,*args):
        cur=self.query(sql,args);row=cur.fetchone()
        return dict(zip([c.name for c in cur.description],row,strict=True)) if row else None


def connection():
    import psycopg
    return psycopg.connect(os.environ['SPORTSBET_TEST_DATABASE_URL'].replace('postgresql+psycopg://','postgresql://',1))


@pytest.mark.parametrize('prop,column',[('pass_yds','passing_yards'),('rush_yds','rushing_yards')])
def test_nfl_nonreceiving_context_excludes_late_stats_snaps_and_tenure(prop,column):
    from tests.test_nfl_participation_evidence import context_item
    from sportsbet.ingestion.provenance import row_sha256,stat_row_sha256
    token=uuid.uuid4().hex[:12];player='ctx-'+token;participant='pfr'+token
    candidate=dict(player='Context fixture',status='Out',position='WR',team='NE',stat_team='NE',relationship='teammate',unit='offense',participant_id=participant)
    with connection() as conn:
        try:
            for week,value in ((1,10),(2,100),(3,30)):
                item=context_item(week,value);g=item['game'];stat=item['stat'];snap=item['snaps'][0]
                stat.update(player_id=player,source_observed_at=LATE if week==2 else NOW)
                stat[column]=value;stat['source_record_sha256']=stat_row_sha256('nfl',stat)
                snap.update(pfr_player_id=participant,source_observed_at=LATE if week==3 else NOW)
                fields={k:v for k,v in snap.items() if not k.startswith('source_')}
                snap['source_record_sha256']=row_sha256(fields)
                for table,row in (('games',g),('player_stats',stat),('nfl_snap_counts',snap)):
                    conn.execute('INSERT INTO public.'+table+' ('+','.join(row)+') VALUES ('+','.join(['%s']*len(row))+')',tuple(row.values()))
            def run(stamp):return asyncio.run(_nfl_split(ContextConnection(conn),player,2024,date(2026,9,30),prop,15.5,'over',candidate,stamp))
            earlier=run(NOW)
            assert earlier['active']==dict(games=1,mean=10.0,hit_rate=0.0) and earlier['unknown_games']==1
            assert earlier['sample_window']['unknown']==dict(oldest='2026-09-04',newest='2026-09-04')
            assert earlier['recent_window']['active']==earlier['active']
            assert earlier['recent_window']['unknown_games']==1
            later=run(LATE)
            assert later['active']==dict(games=3,mean=46.67,hit_rate=.6667) and later['unknown_games']==0
            assert later['recent_window']['active']==later['active']
            assert later['recent_window']['unknown_games']==0
            assert run(None)['active']==later['active']
            conn.execute('UPDATE public.nfl_snap_counts SET source_observed_at=%s WHERE pfr_player_id=%s',(LATE,participant))
            assert run(NOW) is None
            before=conn.execute('SELECT source_record_sha256 FROM player_stats WHERE player_id=%s AND week=1',(player,)).fetchone()[0]
            conn.execute('UPDATE player_stats SET source_record_sha256=%s WHERE player_id=%s AND week=1',('b'*64,player))
            assert run(LATE) is None  # Correctly shaped hashes must replay.
            conn.execute('UPDATE player_stats SET source_record_sha256=%s WHERE player_id=%s AND week=1',(before,player))
            assert run(LATE)['active']['games']==3
            conn.execute('UPDATE nfl_snap_counts SET source_record_sha256=%s WHERE pfr_player_id=%s AND week=1',('b'*64,participant))
            assert run(LATE) is None
        finally:conn.rollback()



def test_nba_legacy_minutes_cannot_establish_context_proof():
    token=uuid.uuid4().hex[:12];name='Context '+token
    candidate=dict(player=name,status='Out',position='SG',team='BOS',stat_team='BOS',relationship='teammate',unit='offense')
    with connection() as conn:
        try:
            for player,minutes in ((800000001,20),(800000002,0)):
                conn.execute("""INSERT INTO public.nba_player_gamelogs
                    (player_id,player_name,game_id,game_date,season,team_abbreviation,points,minutes,
                     source_provider,source_sha256,source_record_sha256,source_observed_at)
                    VALUES(%s,%s,%s,'2026-01-01',2025,'BOS',10,%s,'nba',%s,%s,%s)""",
                    (player,name,token,minutes,'a'*64,'b'*64,NOW))
            assert asyncio.run(_nba_split(ContextConnection(conn),'800000001',2024,
                date(2026,9,30),'points',15.5,'over',candidate,NOW)) is None
        finally:conn.rollback()



def test_tracking_observation_cutoff_precedes_latest_eight_window():
    from sportsbet.prop.ngs_evidence import load_ngs_evidence
    from sportsbet.ingestion.ngs import normalize_asset
    from tests.test_ngs_partition_postgres import EvidencePool, replace
    from tests.test_ngs_ingestion import parquet
    with connection() as conn:
        try:
            conn.execute("INSERT INTO public.games(game_id,season,week,home_team,away_team,game_date) VALUES('ngs-cutoff-fixture',2026,3,'NE','NYJ','2026-09-30')")
            from datetime import datetime, timezone
            observed=datetime.now(timezone.utc)-timedelta(minutes=5)
            base=dict(player_gsis_id='00-9999999',team_abbr='NE',player_position='WR',
                avg_cushion=5.,avg_yac=3.,avg_yac_above_expectation=1.,catch_percentage=50.,targets=4,receptions=2)
            source=[base|dict(season=2025,week=w,avg_separation=1.) for w in range(10,18)]
            source += [base|dict(season=2026,week=w,avg_separation=v) for w,v in ((2,8.),(3,999.))]
            for year in (2025,2026):replace(conn,normalize_asset(parquet(source),year,'receiving',observed)[0])
            first_at=conn.execute('SELECT max(recorded_at) FROM ngs_partition_versions').fetchone()[0]
            source.append(base|dict(season=2026,week=1,avg_separation=100.))
            for year in (2025,2026):replace(conn,normalize_asset(parquet(source),year,'receiving',observed+timedelta(minutes=1))[0])
            later_at=conn.execute('SELECT max(recorded_at) FROM ngs_partition_versions').fetchone()[0]
            pool=EvidencePool(conn)
            def run(stamp):return asyncio.run(load_ngs_evidence(pool,player_gsis_id='00-9999999',season=2026,game_date=date(2026,9,30),team='NE',prop_type='rec_yds',observed_before=stamp))
            earlier=run(first_at);assert earlier['sample_weeks']==8 and earlier['metrics']['avg_separation']==1.875
            later=run(later_at);assert later['sample_weeks']==8 and later['metrics']['avg_separation']==14.25
            assert earlier['sample_periods']==[dict(season=2026,week=2,team='NE')]+[dict(season=2025,week=w,team='NE') for w in range(17,10,-1)]
            assert later['sample_periods']==[dict(season=2026,week=w,team='NE') for w in (2,1)]+[dict(season=2025,week=w,team='NE') for w in range(17,11,-1)]
            assert earlier['roster_team']==later['roster_team']=='NE'
            assert run(first_at-timedelta(seconds=1)) is None
            assert run(first_at)==earlier
            assert 'observed_before' not in run(None)
        finally:conn.rollback()
