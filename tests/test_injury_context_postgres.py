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
    token=uuid.uuid4().hex[:12];player='context-'+token;participant='pfr'+token
    candidate=dict(player='Context fixture',status='Out',position='WR',team='NE',stat_team='NE',relationship='teammate',unit='offense',participant_id=participant)
    with connection() as conn:
        try:
            for week,value in ((1,10),(2,100),(3,30)):
                game=token+str(week)
                conn.execute('INSERT INTO public.games(game_id,season,week,home_team,away_team,game_date) VALUES(%s,2025,%s,%s,%s,%s)',(game,week,'NE','NYJ',date(2025,9,week+1)))
                conn.execute('INSERT INTO public.player_stats(player_id,season,week,team,'+column+',source_provider,source_sha256,source_record_sha256,source_observed_at) VALUES(%s,2025,%s,%s,%s,%s,%s,%s,%s)',(player,week,'NE',value,'nflverse','a'*64,'b'*64,LATE if week==2 else NOW))
                conn.execute('INSERT INTO public.nfl_snap_counts(game_id,season,week,player_name,pfr_player_id,team,opponent,offense_snaps,defense_snaps,source_provider,source_sha256,source_record_sha256,source_observed_at) VALUES(%s,2025,%s,%s,%s,%s,%s,20,0,%s,%s,%s,%s)',(game,week,'Context fixture',participant,'NE','NYJ','nflverse','a'*64,'b'*64,LATE if week==3 else NOW))
            def run(stamp):return asyncio.run(_nfl_split(ContextConnection(conn),player,2024,date(2026,9,30),prop,15.5,'over',candidate,stamp))
            earlier=run(NOW)
            assert earlier['active']==dict(games=1,mean=10.0,hit_rate=0.0)
            assert earlier['unknown_games']==1
            later=run(LATE)
            assert later['active']==dict(games=3,mean=46.67,hit_rate=.6667) and later['unknown_games']==0
            assert run(None)==later  # Legacy no-cutoff interface retained.
            conn.execute('UPDATE public.nfl_snap_counts SET source_observed_at=%s WHERE pfr_player_id=%s',(LATE,participant))
            assert run(NOW) is None
        finally:conn.rollback()


def test_nba_context_excludes_late_identity_stats_minutes_and_tenure():
    token=uuid.uuid4().hex[:12];name='Context '+token;subject=800000001;participant=800000002
    candidate=dict(player=name,status='Out',position='SG',team='BOS',stat_team='BOS',relationship='teammate',unit='offense')
    with connection() as conn:
        try:
            def insert(player,game,day,points,observed,minutes=20,player_name=None):
                conn.execute('''INSERT INTO public.nba_player_gamelogs(player_id,player_name,game_id,game_date,season,team_abbreviation,points,rebounds,assists,minutes,source_provider,source_sha256,source_record_sha256,source_observed_at)
                    VALUES(%s,%s,%s,%s,2025,'BOS',%s,0,0,%s,'nba',%s,%s,%s)''',(player,player_name or name,game,day,points,minutes,'a'*64,'b'*64,observed))
            for day,value in ((1,10),(2,100),(3,30)):
                game=token+str(day)
                insert(subject,game,date(2026,9,day),value,LATE if day==2 else NOW,player_name='Target '+token)
                insert(participant,game,date(2026,9,day),0,LATE if day==3 else NOW)
            # Neither a late identity receipt nor a future game may make the
            # pre-cutoff participant binding ambiguous.
            insert(800000003,token+'late',date(2026,9,1),0,LATE)
            insert(800000004,token+'future',date(2026,10,1),0,NOW)
            def run(stamp):return asyncio.run(_nba_split(ContextConnection(conn),str(subject),2024,date(2026,9,30),'points',15.5,'over',candidate,stamp))
            earlier=run(NOW)
            assert earlier['active']==dict(games=1,mean=10.0,hit_rate=0.0) and earlier['unknown_games']==1
            assert run(LATE) is None  # A genuinely ambiguous available identity is rejected.
            conn.execute('DELETE FROM public.nba_player_gamelogs WHERE player_name=%s AND player_id IN (800000003,800000004)',(name,))
            later=run(LATE)
            assert later['active']==dict(games=3,mean=46.67,hit_rate=.6667) and later['unknown_games']==0
            assert run(None)==later
            conn.execute('UPDATE public.nba_player_gamelogs SET source_observed_at=%s WHERE player_name=%s',(LATE,name))
            assert run(NOW) is None
        finally:conn.rollback()


def test_tracking_observation_cutoff_precedes_latest_eight_window():
    from sportsbet.prop.ngs_evidence import load_ngs_evidence
    from tests.test_ngs_evidence import _Context
    from unittest.mock import MagicMock
    with connection() as conn:
        try:
            conn.execute("INSERT INTO public.games(game_id,season,week,home_team,away_team,game_date) VALUES('ngs-cutoff-fixture',2026,3,'NE','NYJ','2026-09-30')")
            for season,week,value,observed in [(2025,w,1,NOW) for w in range(10,18)]+[(2026,1,100,LATE),(2026,2,8,NOW),(2026,3,999,NOW)]:
                conn.execute('''INSERT INTO public.ngs_stats(player_gsis_id,season,week,stat_type,avg_separation,source_provider,source_url,source_sha256,source_observed_at)
                    VALUES('00-9999999',%s,%s,'receiving',%s,'nflverse_ngs',%s,%s,%s)''',(season,week,value,'https://github.com/nflverse/nflverse-data/releases/download/nextgen_stats/ngs_receiving.parquet','a'*64,observed))
            pool=MagicMock();pool.acquire.return_value=_Context(ContextConnection(conn))
            def run(stamp):return asyncio.run(load_ngs_evidence(pool,player_gsis_id='00-9999999',season=2026,game_date=date(2026,9,30),team='NE',prop_type='rec_yds',observed_before=stamp))
            earlier=run(NOW);assert earlier['sample_weeks']==8 and earlier['metrics']['avg_separation']==1.875
            later=run(LATE);assert later['sample_weeks']==8 and later['metrics']['avg_separation']==14.25
            assert run(NOW-timedelta(seconds=1)) is None
            assert 'observed_before' not in run(None)
        finally:conn.rollback()
