import asyncio
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from unittest.mock import AsyncMock,MagicMock
import pytest
from sportsbet import scan
from sportsbet.config import settings
from sportsbet.graph.models import EVSignal,PropResult
from sportsbet.ledger import Ledger

@pytest.mark.parametrize('sport',['nfl','nba'])
@pytest.mark.parametrize('delay,start_after,availability_age,expected',[
    (301,7200,0,'stale_quote'),(61,60,0,'game_started'),
    (10,3605,0,'game_locked'),
    (10,7200,3595,'availability_unavailable'),(10,7200,0,'accepted'),
    (-1,7200,0,'accepted'),(-2,7200,0,'accepted'),
    (-3,7200,0,'teammate_availability_unmodeled'),
])
async def test_admission_rechecks_time_after_context_queries(tmp_path,monkeypatch,sport,delay,start_after,availability_age,expected):
    initial=datetime(2026,9,30,12,tzinfo=timezone.utc);clock=[initial]
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return clock[0]
    monkeypatch.setattr(scan,'datetime',Clock)
    monkeypatch.setattr('sportsbet.ledger.datetime',Clock)
    monkeypatch.setattr(settings,'history_shadow_enabled',False)
    monkeypatch.setattr(settings,'role_history_shadow_enabled',False)
    market='player_pass_yds' if sport=='nfl' else 'player_points'
    player_id='00-0037248' if sport=='nfl' else '123'
    event=dict(id='timing-fixture',home_team='Home',away_team='Away',commence_time=(initial+timedelta(seconds=start_after)).isoformat(),
        bookmakers=[dict(key='book',last_update=initial.isoformat(),markets=[dict(key=market,
            outcomes=[dict(name='Over',description='Player',point=20.5,price=100)])])])
    context=dict(status='observed',captured_at=(initial-timedelta(seconds=availability_age)).isoformat(),source_url='source',source_sha256='a'*64,
        teams=[dict(abbreviation='KC' if sport=='nfl' else 'BOS',roster_names=['Player'],roster_statuses={'Player':'Active'},
            roster_source_url='roster',roster_source_sha256='b'*64,
            reports=([dict(player='Teammate',position='WR' if sport=='nfl' else 'PG',
                status='Out',reported_at=initial.isoformat())] if delay==-3 else []))])
    connection=AsyncMock();connection.fetch.return_value=[dict(normalized_name='player',player_id=player_id)]
    pool=MagicMock();pool.acquire.return_value.__aenter__=AsyncMock(return_value=connection)
    monkeypatch.setattr(scan,'write_player_prop_snapshots',AsyncMock())
    prop=PropResult(true_probability=Decimal('.65'),sample_size=40,mean_stat=Decimal('24'),
        confidence_interval=(Decimal('.60'),Decimal('.70')),history_source_verified=True)
    signal=EVSignal(ev_percentage=Decimal('.15'),true_probability=Decimal('.65'),implied_probability=Decimal('.5'),
        kelly_fraction=Decimal('.01'),confidence_interval=prop.confidence_interval,trade_plan=['one','two','three'],
        market_type=market,game_id=event['id'],player_name='Player')
    graph=MagicMock();graph.ainvoke=AsyncMock(return_value={('prop_result' if sport=='nfl' else 'nba_prop_result'):prop,'ev_signal':signal})
    monkeypatch.setattr(scan,'create_graph',lambda **kwargs:graph)
    async def slow_context(*args,**kwargs):
        if delay in (-1,-3): raise RuntimeError('optional participation query failed')
        if delay==-2:
            await asyncio.sleep(.1)
            return []
        clock[0]=initial+timedelta(seconds=delay)
        return []
    monkeypatch.setattr(scan,'historical_availability_splits',slow_context)
    if delay==-2: monkeypatch.setattr(scan,'CONTEXT_QUERY_TIMEOUT_SECONDS',.001)
    monkeypatch.setattr(scan,'load_ngs_evidence',AsyncMock(return_value=None))
    ledger=Ledger(tmp_path/'timing.sqlite',database_url='')
    paper_calls=[]
    async def check_model_paper_after_commit(actual_pool,payloads,actual_sport):
        persisted=ledger.predictions()
        assert actual_pool is pool and actual_sport==sport
        assert {p['prediction_id'] for p in payloads}=={p['prediction_id'] for p in persisted}
        assert [p['gate_reason'] for p in payloads]==[p['gate_reason'] for p in persisted]
        paper_calls.append(payloads)
    monkeypatch.setattr('sportsbet.quant.model_selection_paper.record',check_model_paper_after_commit)
    result=await scan.evaluate_event(pool,event,sport,ledger,'scan',context)
    assert len(paper_calls)==1
    row,=ledger.predictions();public,=result['signals']
    assert row['gate_reason']==public['gate_reason']==expected
    assert row['accepted']==(expected=='accepted')
    assert row['captured_at']==public['captured_at']==clock[0].isoformat()
    assert row['model_probability']==public['true_prob']==.65
    assert row['stake_fraction']==(.01 if expected=='accepted' else 0)
    if delay<0: assert 'context_splits' not in row['availability']
    if delay==-3: assert row['availability']['teammates'][0]['player']=='Teammate'
    with ledger.connect() as db:
        assert db.execute('SELECT count(*) FROM exposure').fetchone()[0]==int(expected=='accepted')

@pytest.mark.parametrize('phase',['lock','queries'])
@pytest.mark.parametrize('delay,start_after,availability_age,expected',[
    (301,7200,0,'stale_quote'),(3661,3660,0,'game_started'),
    (301,3900,0,'game_locked'),
    (10,7200,3595,'availability_unavailable'),(10,7200,0,'accepted'),
])
def test_reservation_rechecks_deadlines_after_database_waits(tmp_path,monkeypatch,phase,delay,start_after,availability_age,expected):
    from contextlib import contextmanager
    from tests.test_ledger_and_risk import sig
    initial=datetime(2026,9,30,12,tzinfo=timezone.utc);clock=[initial]
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return clock[0]
    monkeypatch.setattr('sportsbet.ledger.datetime',Clock)
    ledger=Ledger(tmp_path/'reservation.sqlite',database_url='');connect=ledger.connect
    @contextmanager
    def delayed_connection():
        with connect() as db:
            class Delayed:
                def execute(self,sql,args=()):
                    result=db.execute(sql,args)
                    if (phase=='lock' and sql=='BEGIN IMMEDIATE') or (phase=='queries' and sql.startswith('SELECT COALESCE')):
                        clock[0]=initial+timedelta(seconds=delay)
                    return result
            yield Delayed()
    monkeypatch.setattr(ledger,'connect',delayed_connection)
    result=ledger.reserve(sig(),20.5,game_start_time=initial+timedelta(seconds=start_after),
        quote_time=initial,availability_time=initial-timedelta(seconds=availability_age))
    assert result==(expected=='accepted',expected)
    with connect() as db:assert db.execute('SELECT count(*) FROM exposure').fetchone()[0]==int(expected=='accepted')


@pytest.mark.parametrize('quote_age,availability_age,start_after,expected',[
    (300,3600,3601,None),(301,0,3601,'stale_quote'),(0,3601,3601,'availability_unavailable'),
    (-60,-60,3601,None),(-61,0,3601,'stale_quote'),(0,-61,3601,'availability_unavailable'),
    (0,0,3600,'game_locked'),
    (0,0,0,'game_started'),
])
def test_admission_preserves_quote_and_availability_limits_with_board_lock(quote_age,availability_age,start_after,expected):
    from sportsbet.prop.admission import admission_timing_reason
    now=datetime(2026,9,30,12,tzinfo=timezone.utc)
    assert admission_timing_reason(now,game_start_time=now+timedelta(seconds=start_after),
        quote_time=now-timedelta(seconds=quote_age),availability_time=now-timedelta(seconds=availability_age))==expected


def test_admission_rejects_naive_timestamps():
    from sportsbet.prop.admission import admission_timing_reason
    now=datetime(2026,9,30,12,tzinfo=timezone.utc)
    with pytest.raises(ValueError,match='aware'):
        admission_timing_reason(now,game_start_time=now.replace(tzinfo=None),quote_time=now,availability_time=now)
