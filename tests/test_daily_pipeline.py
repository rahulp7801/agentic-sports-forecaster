from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import asyncio
import json

import pytest

from sportsbet import daily
from sportsbet import refresh as refresh_module
from sportsbet.ledger import Ledger
from sportsbet.config import settings


@pytest.mark.asyncio
async def test_paid_daily_rejects_raised_caps_before_graph(monkeypatch):
    graph=AsyncMock()
    monkeypatch.setattr(daily,'create_daily_graph',graph)
    for limit in (21, True):
        with pytest.raises(ValueError,match='Invalid pipeline request'):
            await daily.run(['nfl'],'monitor',limit)
    monkeypatch.setattr(settings,'odds_rolling_credit_limit',451)
    with pytest.raises(ValueError,match='Invalid pipeline request'):
        await daily.run(['nfl'],'daily',20)
    graph.assert_not_awaited()


@pytest.fixture(autouse=True)
def schedule_source(monkeypatch):
    monkeypatch.setattr(daily,'collect_schedule',AsyncMock(return_value={
        'status':'complete','captured_at':datetime.now(timezone.utc).isoformat(),'games':[]}))
    monkeypatch.setattr(daily,'load_snapshot',lambda key:None)
    class Audit:
        def report(self,recommendations_only=False,model_version=None,sport=None):
            return {'cohort':'recommendations' if recommendations_only else 'all_predictions',
                'model_version':model_version,'sport':sport or 'all'}
        def predictions(self): return []
    monkeypatch.setattr(daily,'Ledger',Audit)
    monkeypatch.setattr(daily,'settle_final_props',lambda ledger,sport,schedule:{
        'sport':sport,'status':'complete','candidates':0,'settled':0,'pending':0,
        'reasons':{},'execution_ready':False})
    async def profiles(sports,**kwargs):
        return {sport:profile_counts() for sport in sports}
    monkeypatch.setattr(daily,'refresh_profiles',AsyncMock(side_effect=profiles))


def profile_counts(**changes):
    return dict(dict(profiles=1,unavailable=0,signal_identities=0,public_identities=1,
        public_input_status='observed',selected_events=1,selected_players=1),**changes)


@pytest.mark.asyncio
async def test_actual_daily_graph_isolates_refresh_failure_and_orders_paid_stages(monkeypatch):
    stored={}; calls=[]
    monkeypatch.setattr(daily,'publish_snapshot',lambda key,value:stored.update({key:deepcopy(value)}))
    monkeypatch.setattr(refresh_module,'publish_snapshot',lambda key,value:stored.update({key:deepcopy(value)}))
    def refresh(sport,day,backfill=False):
        calls.append(('refresh',sport))
        if sport=='nfl': raise RuntimeError('provider URL with secret')
    async def watch(sport,limit,count,publish,**kwargs):
        calls.append(('watch',sport))
        return {'sources':{'book':{'status':'observed'}},'captured_at':datetime.now(timezone.utc).isoformat()},None
    async def scan(sports,limit):
        assert sports==['nba']
        assert ('watch','nba') in calls and ('refresh','nba') in calls
        calls.append(('scan','nba'))
        return {'nba':{'status':'complete'}}
    monkeypatch.setattr(refresh_module,'refresh',refresh)
    monkeypatch.setattr(daily,'watch',watch)
    monkeypatch.setattr(daily,'scan',scan)
    report=await daily.run(['nfl','nba'],'daily',20)
    assert report['status']=='degraded'
    assert report['props']['nfl']['status']=='blocked'
    assert report['props']['nba']['status']=='complete'
    assert report['settlements']['nfl']['status']=='blocked'
    assert report['settlements']['nba']['status']=='complete'
    assert report['markets']['nba']['status']=='degraded'  # Unspecified coverage is not complete.
    assert stored['scan:nfl']['reason']=='history_refresh_unavailable'
    assert 'secret' not in str(report)
    assert report['execution_ready'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('status,hours',[('complete',40),('running',1),('failed',1),('complete',-1)])
async def test_monitor_cannot_use_old_failed_incomplete_or_future_refreshes(monkeypatch,status,hours):
    monkeypatch.setattr(daily,'load_snapshot',lambda key:dict(status=status,
        finished_at=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()))
    monkeypatch.setattr(daily,'publish_snapshot',lambda *args:None)
    scan=AsyncMock();watch=AsyncMock(return_value=({'sources':{'kalshi':{'status':'observed','partial_coverage':False}},
        'captured_at':datetime.now(timezone.utc).isoformat()},None))
    monkeypatch.setattr(daily,'scan',scan);monkeypatch.setattr(daily,'watch',watch)
    result=await daily.run(['nfl'],'monitor',20)
    assert result['props']['nfl']['status']=='blocked'
    scan.assert_not_called()
    watch.assert_awaited_once_with('nfl',20,daily.DEFAULT_GAME_LIMIT,True,credit_holdback=12,sportsbook_cadence_hours=6)


@pytest.mark.asyncio
async def test_monitor_uses_recent_history_and_refreshes_markets_before_props(monkeypatch):
    monkeypatch.setattr(daily,'load_snapshot',lambda key:dict(status='complete',finished_at=datetime.now(timezone.utc).isoformat()))
    monkeypatch.setattr(daily,'publish_snapshot',lambda *args:None)
    watch=AsyncMock(return_value=({'sources':{'kalshi':{'status':'observed','partial_coverage':False}},
        'captured_at':datetime.now(timezone.utc).isoformat()},None))
    async def scan_ready(sports,limit):
        watch.assert_awaited_once_with('nba',20,daily.DEFAULT_GAME_LIMIT,True,credit_holdback=9,sportsbook_cadence_hours=6)
        return {'nba':{'status':'complete'}}
    scan=AsyncMock(side_effect=scan_ready)
    monkeypatch.setattr(daily,'scan',scan);monkeypatch.setattr(daily,'watch',watch)
    assert (await daily.run(['nba'],'monitor',20))['status']=='complete'
    scan.assert_awaited_once_with(['nba'],20)


@pytest.mark.asyncio
async def test_daily_settles_observed_stats_before_scanning_new_props(monkeypatch):
    calls=[];stored={}
    monkeypatch.setattr(daily,'publish_snapshot',lambda key,value:stored.update({key:deepcopy(value)}))
    monkeypatch.setattr(daily,'refresh_history',lambda sport,day:(calls.append(('refresh',sport)) or {'status':'complete'}))
    monkeypatch.setattr(daily,'settle_final_props',lambda ledger,sport,schedule:
        (calls.append(('settle',sport)) or {'status':'complete','settled':1,'pending':0}))
    monkeypatch.setattr(daily,'watch',AsyncMock(return_value=({'sources':{'kalshi':{
        'status':'observed','partial_coverage':False}},'captured_at':datetime.now(timezone.utc).isoformat()},None)))
    async def scan(sports,limit):
        assert ('settle','nba') in calls
        calls.append(('scan','nba'))
        return {'nba':{'status':'complete'}}
    monkeypatch.setattr(daily,'scan',scan)
    result=await daily.run(['nba'],'daily',20)
    assert result['status']=='complete' and calls.index(('settle','nba'))<calls.index(('scan','nba'))
    assert stored['metrics:all']['cohort']=='all_predictions'
    assert stored['metrics:recommendations']['cohort']=='recommendations'
    assert stored['metrics:all:nba']['sport']=='nba'
    assert stored['metrics:recommendations:nba']['sport']=='nba'
    assert stored['picks:nba']['selection_policy_version']=='pregame-t60-v1'
    assert stored['metrics:all']['model_version']==stored['metrics:recommendations']['model_version']=='empirical-jeffreys-v4'


@pytest.mark.asyncio
async def test_daily_uses_catchup_evidence_but_publishes_current_schedule_only(monkeypatch):
    stored={};settled=[]
    current={'status':'complete','captured_at':datetime.now(timezone.utc).isoformat(),
        'games':[{'label':'Yesterday'},{'label':'Today'},{'label':'Tomorrow'}],
        'failures':[],'sources':['current']}
    older={'status':'complete','captured_at':datetime.now(timezone.utc).isoformat(),
        'games':[{'label':'2026-09-05'}],'failures':[],'sources':['older']}
    future={'status':'complete','captured_at':current['captured_at'],'games':[{'label':'2026-09-20'}]}
    collector=AsyncMock(side_effect=[current,older,future])
    monkeypatch.setattr(daily,'collect_schedule',collector)
    monkeypatch.setattr(daily,'pending_schedule_offsets',lambda ledger,sport,now:(-30,-8))
    monkeypatch.setattr(daily,'publish_snapshot',lambda key,value:stored.update({key:deepcopy(value)}))
    monkeypatch.setattr(daily,'refresh_history',lambda *args:{'status':'complete'})
    monkeypatch.setattr(daily,'settle_final_props',lambda ledger,sport,schedule:
        (settled.append(schedule) or {'status':'complete','settled':0,'pending':0}))
    monkeypatch.setattr(daily,'watch',AsyncMock(return_value=({'sources':{'kalshi':{
        'status':'observed','partial_coverage':False}},'captured_at':datetime.now(timezone.utc).isoformat()},None)))
    monkeypatch.setattr(daily,'scan',AsyncMock(return_value={'nfl':{'status':'complete'}}))
    report=await daily.run(['nfl'],'daily',20)
    assert report['status']=='complete'
    assert collector.await_count==3
    current_call,older_call,future_call=collector.await_args_list
    assert current_call.args[0]=='nfl' and current_call.args[1] is older_call.args[1]
    assert current_call.kwargs=={}
    assert older_call.kwargs=={'offsets':(-30,-8,-7,-6,-5,-4,-3,-2)}
    assert future_call.kwargs=={'offsets':(2,3,4,5,6)}
    assert [game['label'] for game in stored['slate:nfl']['games']]==['Yesterday','Today','Tomorrow','2026-09-20']
    assert [game['label'] for game in stored['schedule:nfl']['games']]==['Yesterday','Today','Tomorrow']
    assert [game['label'] for game in settled[0]['games']]==['2026-09-05','Yesterday','Today','Tomorrow']


@pytest.mark.asyncio
async def test_catchup_failure_degrades_settlement_without_hiding_current_schedule(monkeypatch):
    stored={};settled=[]
    current={'status':'complete','captured_at':datetime.now(timezone.utc).isoformat(),
        'games':[{'label':'Today'}],'failures':[],'sources':['current']}
    older={'status':'unavailable','captured_at':datetime.now(timezone.utc).isoformat(),
        'games':[],'failures':[{'date':'old'}],'sources':[]}
    monkeypatch.setattr(daily,'collect_schedule',AsyncMock(side_effect=[current,older,current]))
    monkeypatch.setattr(daily,'publish_snapshot',lambda key,value:stored.update({key:deepcopy(value)}))
    monkeypatch.setattr(daily,'refresh_history',lambda *args:{'status':'complete'})
    monkeypatch.setattr(daily,'settle_final_props',lambda ledger,sport,schedule:
        (settled.append(schedule) or {'status':'degraded','settled':0,'pending':1}))
    monkeypatch.setattr(daily,'watch',AsyncMock(return_value=({'sources':{'kalshi':{
        'status':'observed','partial_coverage':False}},'captured_at':datetime.now(timezone.utc).isoformat()},None)))
    scan=AsyncMock(return_value={'nba':{'status':'complete'}});monkeypatch.setattr(daily,'scan',scan)
    report=await daily.run(['nba'],'daily',20)
    assert report['status']=='degraded' and report['schedules']['nba']['status']=='complete'
    assert stored['schedule:nba']==current and settled[0]['status']=='partial'
    scan.assert_awaited_once()


@pytest.mark.asyncio
async def test_future_schedule_failure_keeps_current_fixtures_and_marks_partial_slate(monkeypatch):
    stored={}
    current={'status':'complete','captured_at':datetime.now(timezone.utc).isoformat(),
        'games':[{'label':'Today'}],'sources':['current'],'failures':[]}
    future={'status':'unavailable','captured_at':current['captured_at'],'games':[],
        'sources':[],'failures':[{'date':'20260920','error_type':'HTTPStatusError'}]}
    monkeypatch.setattr(daily,'collect_schedule',AsyncMock(side_effect=[current,future]))
    monkeypatch.setattr(daily,'publish_snapshot',lambda key,value:stored.update({key:deepcopy(value)}))
    monkeypatch.setattr(daily,'watch',AsyncMock(return_value=({'sources':{'kalshi':{
        'status':'observed','partial_coverage':False}},'captured_at':current['captured_at']},None)))
    result=await daily.run(['nfl'],'public_monitor',25)
    assert stored['schedule:nfl']==current
    assert stored['slate:nfl']['games']==current['games'] and stored['slate:nfl']['partial'] is True
    assert result['schedules']['nfl']['slate_status']=='partial'


@pytest.mark.asyncio
async def test_settlement_failure_is_redacted_and_degrades_without_suppressing_scan(monkeypatch):
    monkeypatch.setattr(daily,'load_snapshot',lambda key:dict(
        status='complete',finished_at=datetime.now(timezone.utc).isoformat()))
    monkeypatch.setattr(daily,'publish_snapshot',lambda *args:None)
    monkeypatch.setattr(daily,'settle_final_props',lambda *args:(_ for _ in ()).throw(
        RuntimeError('provider URL with secret')))
    monkeypatch.setattr(daily,'watch',AsyncMock(return_value=({'sources':{'kalshi':{
        'status':'observed','partial_coverage':False}},'captured_at':datetime.now(timezone.utc).isoformat()},None)))
    scan=AsyncMock(return_value={'nba':{'status':'complete'}});monkeypatch.setattr(daily,'scan',scan)
    result=await daily.run(['nba'],'monitor',20)
    assert result['status']=='degraded' and result['settlements']['nba']=={
        'status':'failed','error_type':'RuntimeError'}
    assert 'secret' not in str(result)
    scan.assert_awaited_once()


@pytest.mark.asyncio
async def test_full_monitor_real_collector_shares_budget_and_preserves_other_venues(monkeypatch,tmp_path):
    import json
    import httpx
    from sportsbet import market_watch
    ledger=Ledger(tmp_path/'credits.sqlite')
    stored={};requests=[]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings,'odds_api_key','fixture')
    monkeypatch.setattr(settings,'analytics_database_url','postgresql://test-only')
    monkeypatch.setattr(market_watch,'Ledger',lambda:ledger)
    monkeypatch.setattr(market_watch,'load_snapshot',lambda key:deepcopy(stored.get(key)))
    monkeypatch.setattr(daily,'load_snapshot',lambda key:dict(status='complete',finished_at=datetime.now(timezone.utc).isoformat()))
    for module in (daily,market_watch):
        monkeypatch.setattr(module,'publish_snapshot',lambda key,value:stored.update({key:deepcopy(value)}))
    def provider(request):
        assert request.method=='GET' and request.url.host=='api.the-odds-api.com'
        requests.append(request)
        return httpx.Response(200,json=[])
    client=httpx.AsyncClient
    transport=httpx.MockTransport(provider)
    monkeypatch.setattr(httpx,'AsyncClient',lambda *args,**kwargs:client(*args,**(kwargs|{'transport':transport})))
    kalshi=AsyncMock(return_value={'status':'observed','games':[],'partial_coverage':False})
    prizepicks=AsyncMock(return_value={'projections':[],'partial_coverage':True})
    monkeypatch.setattr(market_watch,'kalshi_games',kalshi)
    monkeypatch.setattr(market_watch,'capture_projections',prizepicks)
    async def scan(sports,limit):
        assert len(requests)==1 and kalshi.await_count==prizepicks.await_count==2
        assert not ledger.reserve_api_credits(1,limit)  # Prop scans share the spent ceiling.
        return {sport:{'status':'budget_exhausted'} for sport in sports}
    monkeypatch.setattr(daily,'scan',scan)
    result=await daily.run(['nfl','nba'],'monitor',1)
    assert result['status']=='degraded' and len(requests)==1
    assert result['markets']['nfl']['sources']['sportsbook']['status']=='observed'
    assert result['markets']['nba']['sources']['sportsbook']['status']=='budget_exhausted'
    assert all(result['markets'][sport]['sources']['kalshi']['status']=='observed' for sport in ('nfl','nba'))
    archives=list((tmp_path/'.local/market-watch').glob('*.json'))
    assert len(archives)==2
    for path in archives:
        archive=json.loads(path.read_text())
        assert archive['summary']==stored['markets:'+archive['summary']['sport']]
        assert market_watch.comparisons(archive['evidence'])==archive['summary']['comparisons']


def test_rolling_credit_limit_includes_previous_days_and_survives_restart(monkeypatch,tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr(settings,'odds_rolling_credit_limit',6)
    path=tmp_path/'budget.sqlite';ledger=Ledger(path)
    today=datetime.now(timezone.utc).date()
    with ledger.connect() as db:
        db.execute('INSERT INTO api_usage VALUES (?,?)',((today-timedelta(days=1)).isoformat(),5))
        db.execute('INSERT INTO api_usage VALUES (?,?)',((today-timedelta(days=31)).isoformat(),100))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:Ledger(path).reserve_api_credits(1,25),range(4)))
    assert sum(results)==1
    assert not Ledger(path).reserve_api_credits(1,25)
    assert not ledger.reserve_api_credits(True,25)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['public_daily','public_monitor'])
async def test_public_modes_use_real_graph_and_collector_without_paid_or_prop_calls(monkeypatch,tmp_path,mode):
    from sportsbet import market_watch
    stored={}; refreshed=[]
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('KALSHI_PAIR_SOURCE_DIR',raising=False)
    monkeypatch.delenv('KALSHI_PAIR_OUTPUT',raising=False)
    for module in (daily,refresh_module,market_watch):
        monkeypatch.setattr(module,'publish_snapshot',lambda key,value:stored.update({key:deepcopy(value)}))
    def refresh(sport,day,backfill=False):
        refreshed.append(sport)
        return {'provider':'fixture'}
    monkeypatch.setattr(refresh_module,'refresh',refresh)
    def public_market_read(key):
        assert key.startswith('markets:')  # Public modes never read history or credits.
        return None
    monkeypatch.setattr(daily,'load_snapshot',public_market_read)
    def unexpected_credit(*args):raise AssertionError('Public collection must not spend credits')
    monkeypatch.setattr(Ledger,'reserve_api_credits',unexpected_credit)
    books=AsyncMock();prizepicks=AsyncMock(return_value={
        'status':'observed','projections':[],'partial_coverage':False});props=AsyncMock()
    monkeypatch.setattr(market_watch,'sportsbooks',books)
    monkeypatch.setattr(market_watch,'capture_projections',prizepicks)
    monkeypatch.setattr(daily,'scan',props)
    kalshi=AsyncMock(return_value={'status':'observed','games':[],'partial_coverage':True})
    monkeypatch.setattr(market_watch,'kalshi_games',kalshi)
    result=await daily.run(['nfl','nba'],mode,25)
    assert result['status']=='observed' and result['execution_ready'] is False
    assert result['scope']==daily.PUBLIC_SCOPES[mode]
    if mode=='public_daily':
        assert result['markets']['nfl']['research_pair_status']=='not_configured'
    else:
        assert 'research_pair_status' not in result['markets']['nfl']
    assert refreshed==(['nfl','nba'] if mode=='public_daily' else [])
    assert kalshi.await_count==2
    books.assert_not_called();props.assert_not_called()
    assert prizepicks.await_count==(2 if mode=='public_daily' else 0)
    assert all(value['status']=='not_requested' for value in result['props'].values())
    expected='complete' if mode=='public_daily' else 'not_requested'
    assert all(value['status']==expected for value in result['settlements'].values())
    if mode=='public_monitor':
        assert all(value['reason']=='monitor_mode' for value in result['settlements'].values())
        assert 'History refresh' in result['scope'] and 'not requested' in result['scope']
    else:
        assert 'history refresh' in result['scope'] and 'settlement evaluation' in result['scope']
    assert not any(key.startswith('scan:') for key in stored)
    assert {'schedule:nfl','schedule:nba','markets:nfl','markets:nba','pipeline:'+mode}<=set(stored)
    for sport in ('nfl','nba'):
        assert result['markets'][sport]['sources']['kalshi']['partial_coverage'] is True
        assert result['markets'][sport]['sources']['sportsbook']['status']=='not_requested'
        assert result['markets'][sport]['sources']['prizepicks']['status']==(
            'observed' if mode=='public_daily' else 'not_requested')
    assert len(list((tmp_path/'.local/market-watch').glob('*.json')))==2


@pytest.mark.asyncio
async def test_public_daily_pairs_existing_nfl_archive_without_exposing_private_rows(monkeypatch,tmp_path):
    from sportsbet.quant import kalshi_pair_capture as pair_module
    from sportsbet.quant import kalshi_ask_policy as ask_policy
    from sportsbet.quant import kalshi_prior20_ask_policy as prior20_policy
    archive=tmp_path/'market.json'
    archive.write_text(json.dumps({'source':'already_collected'}),encoding='utf-8')
    source_dir=tmp_path/'sources'
    source_dir.mkdir()
    (source_dir/'source-manifest.json').write_text('{"source":"prequote"}',encoding='utf-8')
    calls=[];published={}
    monkeypatch.setenv('KALSHI_PAIR_SOURCE_DIR',str(source_dir))
    monkeypatch.setenv('KALSHI_PAIR_OUTPUT',str(tmp_path/'private'/'pair.json'))
    monkeypatch.setattr(daily,'publish_snapshot',lambda key,value:published.update({key:deepcopy(value)}))
    monkeypatch.setattr(daily,'refresh_history',lambda *args:{'status':'complete'})
    monkeypatch.setattr(daily,'watch',AsyncMock(return_value=({'sources':{'kalshi':{
        'status':'observed','partial_coverage':False}},
        'captured_at':datetime.now(timezone.utc).isoformat()},archive)))
    monkeypatch.setattr(pair_module,'capture',lambda market,source_dir,*,started_at,source_manifest:
            (calls.append((market,source_dir,started_at,source_manifest)) or {'private_forecasts':[1]}))
    monkeypatch.setattr(ask_policy,'freeze',lambda value:{'candidates_count':0})
    monkeypatch.setattr(prior20_policy,'freeze',lambda value:{'candidates_count':1})
    monkeypatch.setattr(pair_module,'save_pair',lambda value,output:
        calls.append((value,output)))
    result=await daily.run(['nfl'],'public_daily',25)
    assert result['status']=='observed'
    assert result['markets']['nfl']['research_pair_status']=='captured_local'
    assert len(calls)==2 and calls[0][0]=={'source':'already_collected'}
    assert calls[0][3]=={'source':'prequote'}
    assert calls[1][0]=={'private_forecasts':[1], 'ask_policy':{'candidates_count':0},
                         'prior20_ask_policy':{'candidates_count':1}}
    assert all('private_forecasts' not in str(value) for value in published.values())


@pytest.mark.asyncio
async def test_failed_private_pair_does_not_change_public_collection(monkeypatch,tmp_path):
    from sportsbet.quant import kalshi_pair_capture as pair_module
    archive=tmp_path/'market.json'
    archive.write_text('{}',encoding='utf-8')
    source_dir=tmp_path/'sources'
    source_dir.mkdir()
    (source_dir/'source-manifest.json').write_text('{}',encoding='utf-8')
    monkeypatch.setenv('KALSHI_PAIR_SOURCE_DIR',str(source_dir))
    monkeypatch.setenv('KALSHI_PAIR_OUTPUT',str(tmp_path/'private'/'pair.json'))
    monkeypatch.setattr(daily,'publish_snapshot',lambda *args:None)
    monkeypatch.setattr(daily,'refresh_history',lambda *args:{'status':'complete'})
    monkeypatch.setattr(daily,'watch',AsyncMock(return_value=({'sources':{'kalshi':{
        'status':'observed','partial_coverage':False}},
        'captured_at':datetime.now(timezone.utc).isoformat()},archive)))
    monkeypatch.setattr(pair_module,'capture',lambda *args,**kwargs:
        (_ for _ in ()).throw(ValueError('private detail must stay hidden')))
    result=await daily.run(['nfl'],'public_daily',25)
    assert result['status']=='observed'
    assert result['markets']['nfl']['research_pair_status']=='capture_failed'
    assert 'private detail' not in str(result)
    assert not (tmp_path/'private'/'pair.json').exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('reason',['archive_unavailable','source_unavailable'])
async def test_public_daily_reports_missing_private_pair_input(monkeypatch,tmp_path,reason):
    from sportsbet.quant import kalshi_pair_capture as pair_module
    archive=tmp_path/'market.json'
    archive.write_text('{}',encoding='utf-8')
    source_dir=tmp_path/'sources'
    source_dir.mkdir()  # The source manifest was not staged.
    monkeypatch.setenv('KALSHI_PAIR_SOURCE_DIR',str(source_dir))
    monkeypatch.setenv('KALSHI_PAIR_OUTPUT',str(tmp_path/'private'/'pair.json'))
    monkeypatch.setattr(daily,'publish_snapshot',lambda *args:None)
    monkeypatch.setattr(daily,'refresh_history',lambda *args:{'status':'complete'})
    monkeypatch.setattr(daily,'watch',AsyncMock(return_value=({'sources':{'kalshi':{
        'status':'observed','partial_coverage':False}},
        'captured_at':datetime.now(timezone.utc).isoformat()},
        None if reason=='archive_unavailable' else archive)))
    monkeypatch.setattr(pair_module,'capture',lambda *args,**kwargs:
        pytest.fail('Private model must not run without its inputs'))
    result=await daily.run(['nfl'],'public_daily',25)
    assert result['status']=='observed'
    assert result['markets']['nfl']['research_pair_status']==reason
    assert 'private' not in str(result['markets']['nfl'])


@pytest.mark.asyncio
async def test_public_daily_reports_failed_market_without_private_details(monkeypatch):
    monkeypatch.setattr(daily,'publish_snapshot',lambda *args:None)
    monkeypatch.setattr(daily,'refresh_history',lambda *args:{'status':'complete'})
    monkeypatch.setattr(daily,'watch',AsyncMock(side_effect=RuntimeError('private provider detail')))
    result=await daily.run(['nfl'],'public_daily',25)
    assert result['status']=='degraded'
    assert result['markets']['nfl']['research_pair_status']=='market_unavailable'
    assert 'private provider detail' not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('failed_stage',['markets','schedules','histories'])
async def test_public_failure_is_visible_without_suppressing_other_stages(monkeypatch,failed_stage):
    stored={}
    monkeypatch.setattr(daily,'publish_snapshot',lambda key,value:stored.update({key:deepcopy(value)}))
    monkeypatch.setattr(daily,'refresh_history',lambda *args:{'status':'failed' if failed_stage=='histories' else 'complete'})
    monkeypatch.setattr(daily,'collect_schedule',AsyncMock(return_value={
        'status':'unavailable' if failed_stage=='schedules' else 'complete','captured_at':datetime.now(timezone.utc).isoformat()}))
    watch=AsyncMock(return_value=({'sources':{'kalshi':{'status':'unavailable' if failed_stage=='markets' else 'observed',
        'partial_coverage':True}},'captured_at':datetime.now(timezone.utc).isoformat()},None))
    monkeypatch.setattr(daily,'watch',watch)
    props=AsyncMock();monkeypatch.setattr(daily,'scan',props)
    result=await daily.run(['nfl','nba'],'public_daily',25)
    assert result['status']=='degraded'
    assert watch.await_count==2
    assert set(result['schedules'])==set(result['histories'])=={'nfl','nba'}
    props.assert_not_called()
    assert stored['pipeline:public_daily']['status']=='degraded'


@pytest.mark.asyncio
async def test_paid_daily_cfb_refreshes_settles_and_scans_without_public_sources(monkeypatch):
    calls=[]; stored={}
    monkeypatch.setattr(daily,'publish_snapshot',lambda key,value:stored.update({key:deepcopy(value)}))
    monkeypatch.setattr(daily,'refresh_history',lambda sport,day:(calls.append(('refresh',sport)) or {'status':'complete'}))
    monkeypatch.setattr(daily,'settle_final_props',lambda ledger,sport,schedule:
        (calls.append(('settle',sport)) or {'status':'complete','settled':0,'pending':0}))
    async def watch(sport,limit,count,publish,**kwargs):
        calls.append(('watch',sport))
        return {'sources':{'sportsbook':{'status':'observed','partial_coverage':False},
            'kalshi':{'status':'not_requested','partial_coverage':True},
            'prizepicks':{'status':'not_requested','partial_coverage':True}},
            'captured_at':datetime.now(timezone.utc).isoformat()},None
    async def scan(sports,limit):
        assert sports==['cfb'] and ('settle','cfb') in calls and ('watch','cfb') in calls
        calls.append(('scan','cfb'))
        return {'cfb':{'status':'complete'}}
    monkeypatch.setattr(daily,'watch',watch)
    monkeypatch.setattr(daily,'scan',scan)
    report=await daily.run(['cfb'],'daily',20)
    assert report['status']=='complete'
    assert report['markets']['cfb']['status']=='complete'
    assert stored['picks:cfb']['selection_policy_version']=='pregame-t60-v1'
    assert calls.index(('refresh','cfb'))<calls.index(('settle','cfb'))<calls.index(('scan','cfb'))
    with pytest.raises(ValueError):
        await daily.run(['cfb'],'public_daily',25)


async def test_shadow_report_failure_cannot_change_production_settlement(monkeypatch):
    monkeypatch.setattr(daily,'load_snapshot',lambda key:dict(status='complete',finished_at=datetime.now(timezone.utc).isoformat()))
    stored={}
    def publish(key,value):
        if key.startswith('shadow-validation:'):raise RuntimeError('research storage unavailable')
        stored[key]=value
    monkeypatch.setattr(daily,'publish_snapshot',publish)
    monkeypatch.setattr(daily,'watch',AsyncMock(return_value=({'sources':{'book':{'status':'observed','partial_coverage':False}},
        'captured_at':datetime.now(timezone.utc).isoformat()},None)))
    monkeypatch.setattr(daily,'scan',AsyncMock(return_value={'nba':{'status':'complete'}}))
    result=await daily.run(['nba'],'monitor',20)
    assert result['status']=='complete' and result['settlements']['nba']['status']=='complete'
    assert 'picks:nba' in stored and 'metrics:all:nba' in stored


def _complete_public_snapshot(sport,mode,when):
    return {'schema_version':2,'sport':sport,'captured_at':when.isoformat(),
            'execution_ready':False,'evidence_sha256':'a'*64,'comparisons':[],
            'sources':{'sportsbook':{'status':'not_requested','partial_coverage':True},
                       'kalshi':{'status':'observed','partial_coverage':False},
                       'prizepicks':{'status':'observed' if mode=='public_daily' else 'not_requested',
                                     'partial_coverage':mode!='public_daily'}}}


@pytest.mark.asyncio
@pytest.mark.parametrize('source_mode',('public_monitor','public_daily'))
async def test_public_monitor_reuses_fresh_complete_market_without_provider_calls(monkeypatch,source_mode):
    now=datetime.now(timezone.utc)
    snapshots={sport:_complete_public_snapshot(sport,source_mode,now-timedelta(minutes=2))
               for sport in ('nfl','nba')}
    monkeypatch.setattr(daily,'load_snapshot',lambda key:snapshots[key.split(':')[1]])
    stored={}
    monkeypatch.setattr(daily,'publish_snapshot',lambda key,value:stored.update({key:deepcopy(value)}))
    watch=AsyncMock(side_effect=AssertionError('fresh public source must be reused'))
    monkeypatch.setattr(daily,'watch',watch)
    result=await daily.run(['nfl','nba'],'public_monitor',25)
    assert result['status']=='observed'
    assert all(result['markets'][sport]['captured_at']==snapshots[sport]['captured_at']
               for sport in snapshots)
    watch.assert_not_called()
    assert 'pipeline:public_monitor' in stored


@pytest.mark.asyncio
async def test_public_daily_reports_reused_market_without_private_pair(monkeypatch):
    now=datetime.now(timezone.utc)
    cached=_complete_public_snapshot('nfl','public_daily',now-timedelta(minutes=2))
    monkeypatch.setattr(daily,'load_snapshot',lambda key:cached if key=='markets:nfl' else None)
    monkeypatch.setattr(daily,'publish_snapshot',lambda *args:None)
    monkeypatch.setattr(daily,'refresh_history',lambda *args:{'status':'complete'})
    watch=AsyncMock(side_effect=AssertionError('fresh complete market must be reused'))
    monkeypatch.setattr(daily,'watch',watch)
    result=await daily.run(['nfl'],'public_daily',25)
    assert result['status']=='observed'
    assert result['markets']['nfl']['research_pair_status']=='market_reused'
    watch.assert_not_called()


@pytest.mark.parametrize('fault',('stale','future','partial','wrong_scope','missing_hash','wrong_sport'))
def test_public_market_reuse_fails_closed(fault):
    now=datetime.now(timezone.utc)
    snapshot=_complete_public_snapshot('nfl','public_monitor',now)
    if fault=='stale':snapshot['captured_at']=(now-timedelta(minutes=11)).isoformat()
    if fault=='future':snapshot['captured_at']=(now+timedelta(seconds=1)).isoformat()
    if fault=='partial':snapshot['sources']['kalshi']['partial_coverage']=True
    if fault=='wrong_scope':snapshot['sources']['prizepicks']['status']='observed'
    if fault=='missing_hash':snapshot.pop('evidence_sha256')
    if fault=='wrong_sport':snapshot['sport']='nba'
    assert not daily.reusable_public_market(snapshot,'nfl','public_monitor',now)


def test_public_daily_requires_all_requested_sources():
    now=datetime.now(timezone.utc)
    monitor=_complete_public_snapshot('nfl','public_monitor',now)
    assert not daily.reusable_public_market(monitor,'nfl','public_daily',now)
    complete=_complete_public_snapshot('nfl','public_daily',now)
    assert daily.reusable_public_market(complete,'nfl','public_daily',now)
    complete['sources']['prizepicks']['partial_coverage']=True
    assert not daily.reusable_public_market(complete,'nfl','public_daily',now)

@pytest.mark.asyncio
@pytest.mark.parametrize('event_capture',[False,True])
async def test_nfl_stat_only_failure_does_not_block_existing_research(monkeypatch,event_capture):
    from unittest.mock import MagicMock
    from sportsbet.db import connection
    from sportsbet.quant import nfl_corrected_workload_paper as workload
    from sportsbet.quant import nfl_stat_only_paper as stat_only
    stored = {}
    calls = []
    monkeypatch.setattr(daily, 'publish_snapshot',
                        lambda key, value: stored.update({key: deepcopy(value)}))
    monkeypatch.setattr(daily, 'refresh_history',
                        lambda sport, day: {'status': 'complete'})
    monkeypatch.setattr(daily, 'watch', AsyncMock(return_value=(
        {'sources': {'kalshi': {'status': 'observed', 'partial_coverage': False}},
         'captured_at': datetime.now(timezone.utc).isoformat()}, None)))
    scan_result={'status': 'complete', 'scan_id': 'a'*32}
    if event_capture:
        scan_result['stat_only_capture']={'status':'captured',
                                          'counts':{'attempts':2,'recorded':2}}
    monkeypatch.setattr(daily, 'scan', AsyncMock(return_value={'nfl': scan_result}))
    pool = MagicMock()
    pool.close = AsyncMock()
    monkeypatch.setattr(connection, 'create_async_pool', AsyncMock(return_value=pool))
    async def stat_capture(receipt_pool, scan_id):
        calls.append('stat-only')
        raise RuntimeError('stat-only failed')
    async def workload_capture(receipt_pool, scan_id):
        calls.append('workload')
        return {'status': 'captured'}
    monkeypatch.setattr(stat_only, 'capture', stat_capture)
    monkeypatch.setattr(stat_only, 'report', AsyncMock(return_value={'status':'collecting'}))
    monkeypatch.setattr(workload, 'capture', workload_capture)
    monkeypatch.setattr(workload, 'report', AsyncMock(return_value={'status': 'collecting'}))
    await daily.run(['nfl'], 'daily', 20)
    assert calls == (['workload'] if event_capture else ['stat-only', 'workload'])
    assert stored['research:stat-only-capture:nfl'] == (
        scan_result['stat_only_capture'] if event_capture else
        {'status': 'unavailable', 'error_type': 'RuntimeError'})
    assert stored['research:corrected-workload-capture:nfl']['status'] == 'captured'
    assert stored['corrected-workload-shadow-validation:nfl']['status'] == 'collecting'
    pool.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_public_profiles_consume_exact_fresh_inputs_before_histories_and_catchup_finish(monkeypatch):
    from threading import Event
    profiles_done=asyncio.Event();history_release=Event();calls=[];stored={}
    stamps={sport:(datetime.now(timezone.utc)-timedelta(seconds=index)).isoformat()
            for index,sport in enumerate(('nfl','nba'),1)}
    async def collect(sport,now,**kwargs):
        offsets=kwargs.get('offsets',())
        if offsets and max(offsets)<0:
            await asyncio.wait_for(profiles_done.wait(),3)
            calls.append(('catchup_finished',sport))
        return dict(status='complete',captured_at=stamps[sport],games=[],sources=[],failures=[])
    def history(sport,day):
        assert history_release.wait(3), 'Profiles waited for the history superstep barrier'
        calls.append(('history_finished',sport));return dict(status='complete')
    def catchup_offsets(*args):
        assert history_release.wait(3), 'Catchup offset database reads blocked profile admission'
        calls.append(('offsets_finished',args[1]));return ()
    async def watch(sport,*args,**kwargs):
        calls.append(('market',sport))
        return dict(sources={'kalshi':dict(status='observed',partial_coverage=False)},captured_at=stamps[sport]),None
    async def profiles(sports,*,expected_public_captures):
        sport,=sports
        assert expected_public_captures=={sport:dict(market_captured_at=stamps[sport],slate_captured_at=stamps[sport])}
        assert stored['slate:'+sport]['captured_at']==stamps[sport]
        calls.append(('profiles',sport))
        if sum(stage=='profiles' for stage,_ in calls)==2:
            profiles_done.set();history_release.set()
        return {sport:profile_counts()}
    monkeypatch.setattr(daily,'collect_schedule',collect)
    monkeypatch.setattr(daily,'refresh_history',history)
    monkeypatch.setattr(daily,'pending_schedule_offsets',catchup_offsets)
    monkeypatch.setattr(daily,'watch',watch)
    monkeypatch.setattr(daily,'refresh_profiles',profiles)
    monkeypatch.setattr(daily,'publish_snapshot',lambda key,value:stored.update({key:deepcopy(value)}))
    result=await daily.run(['nfl','nba'],'public_daily',20)
    assert result['status']=='observed'
    for sport in ('nfl','nba'):
        assert calls.count(('market',sport))==calls.count(('profiles',sport))==1
        assert calls.index(('profiles',sport))<calls.index(('catchup_finished','nfl'))
        assert calls.index(('profiles',sport))<calls.index(('history_finished','nfl'))
        assert calls.index(('profiles',sport))<calls.index(('offsets_finished','nfl'))
        assert result['schedules'][sport]['slate_captured_at']==stamps[sport]
        assert result['profiles'][sport]['status']=='complete'


@pytest.mark.asyncio
async def test_profile_failure_preserves_market_receipts_and_next_sport_refresh(monkeypatch):
    stamp=datetime.now(timezone.utc).isoformat();stored={};attempted=[]
    monkeypatch.setattr(daily,'publish_snapshot',lambda key,value:stored.update({key:deepcopy(value)}))
    monkeypatch.setattr(daily,'refresh_history',lambda *args:dict(status='complete'))
    monkeypatch.setattr(daily,'watch',AsyncMock(return_value=(dict(
        captured_at=stamp,sources={'kalshi':dict(status='observed',partial_coverage=False)}),None)))
    async def profiles(sports,**kwargs):
        sport,=sports;attempted.append(sport)
        if sport=='nfl': raise RuntimeError('unlogged private provider response')
        return {sport:profile_counts()}
    monkeypatch.setattr(daily,'refresh_profiles',profiles)
    result=await daily.run(['nfl','nba'],'public_daily',20)
    assert result['status']=='degraded' and attempted==['nfl','nba']
    assert result['profiles']['nfl']==dict(status='failed',error_type='RuntimeError')
    assert result['profiles']['nba']['status']=='complete'
    assert all(result['markets'][sport]['captured_at']==stamp for sport in ('nfl','nba'))
    assert stored['pipeline:public_daily']['markets']==result['markets']
    assert 'unlogged private' not in str(result)


@pytest.mark.asyncio
async def test_failed_market_can_refresh_signal_profiles_without_claiming_public_input(monkeypatch):
    monkeypatch.setattr(daily,'publish_snapshot',lambda *args:None)
    monkeypatch.setattr(daily,'refresh_history',lambda *args:dict(status='complete'))
    monkeypatch.setattr(daily,'watch',AsyncMock(side_effect=RuntimeError('private URL')))
    async def profiles(sports,*,expected_public_captures):
        assert sports==['nfl'] and expected_public_captures['nfl']['market_captured_at'] is None
        return {'nfl':profile_counts(signal_identities=1,public_identities=0,public_input_status='rejected')}
    monkeypatch.setattr(daily,'refresh_profiles',profiles)
    result=await daily.run(['nfl'],'public_daily',20)
    assert result['markets']['nfl']['status']=='failed' and 'captured_at' not in result['markets']['nfl']
    assert result['profiles']['nfl']['profiles']==1 and result['profiles']['nfl']['status']=='degraded'
    assert result['status']=='degraded' and 'private URL' not in str(result)


@pytest.mark.asyncio
async def test_profile_ready_timeout_is_bounded_without_cancelling_schedule_future(monkeypatch):
    released=asyncio.Event();stamp=datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(daily,'PROFILE_READY_TIMEOUT_SECONDS',0.01)
    monkeypatch.setattr(daily,'publish_snapshot',lambda *args:None)
    monkeypatch.setattr(daily,'refresh_history',lambda *args:dict(status='complete'))
    monkeypatch.setattr(daily,'watch',AsyncMock(return_value=(dict(
        captured_at=stamp,sources={'kalshi':dict(status='observed',partial_coverage=False)}),None)))
    async def collect(*args,**kwargs):
        if kwargs.get('offsets')==(2,3,4,5,6): await released.wait()
        return dict(status='complete',captured_at=stamp,games=[])
    async def profiles(sports,*,expected_public_captures):
        assert expected_public_captures['nfl']==dict(market_captured_at=stamp,slate_captured_at=None)
        released.set()
        return {'nfl':profile_counts(profiles=0,public_identities=0,public_input_status='rejected',selected_events=0,selected_players=0)}
    monkeypatch.setattr(daily,'collect_schedule',collect)
    monkeypatch.setattr(daily,'refresh_profiles',profiles)
    result=await asyncio.wait_for(daily.run(['nfl'],'public_daily',20),2)
    assert result['schedules']['nfl']['slate_captured_at']==stamp
    assert result['profiles']['nfl']['status']==result['status']=='degraded'


@pytest.mark.asyncio
async def test_schedule_exception_releases_every_pending_profile_waiter(monkeypatch):
    monkeypatch.setattr(daily,'refresh_history',lambda *args:dict(status='complete'))
    monkeypatch.setattr(daily,'collect_schedule',AsyncMock(side_effect=RuntimeError('schedule unavailable')))
    monkeypatch.setattr(daily,'watch',AsyncMock(return_value=(dict(captured_at=datetime.now(timezone.utc).isoformat(),
        sources={'kalshi':dict(status='observed',partial_coverage=False)}),None)))
    futures={}
    with pytest.raises(RuntimeError,match='schedule unavailable'):
        async for update in daily.create_daily_graph().astream(dict(sports=['nfl','nba'],mode='public_daily',daily_credit_limit=20)):
            if 'initialize' in update: futures=update['initialize']['profile_readiness']
    assert set(futures)=={'nfl','nba'} and all(value.done() and value.result() is None for value in futures.values())


@pytest.mark.asyncio
async def test_cancelled_invocation_releases_waiters_without_swallowing_cancellation(monkeypatch):
    started=asyncio.Event();initial=asyncio.Event();blocked=asyncio.Event();futures={}
    monkeypatch.setattr(daily,'publish_snapshot',lambda *args:None)
    monkeypatch.setattr(daily,'refresh_history',lambda *args:dict(status='complete'))
    async def collect(*args,**kwargs):
        started.set();await blocked.wait()
    monkeypatch.setattr(daily,'collect_schedule',collect)
    monkeypatch.setattr(daily,'watch',AsyncMock(return_value=(dict(captured_at=datetime.now(timezone.utc).isoformat(),
        sources={'kalshi':dict(status='observed',partial_coverage=False)}),None)))
    async def consume():
        nonlocal futures
        async for update in daily.create_daily_graph().astream(dict(sports=['nfl','nba'],mode='public_daily',daily_credit_limit=20)):
            if 'initialize' in update:
                futures=update['initialize']['profile_readiness'];initial.set()
    task=asyncio.create_task(consume())
    await initial.wait();await started.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert all(value.done() and value.result() is None for value in futures.values())
    daily.refresh_profiles.assert_not_called()


@pytest.mark.asyncio
async def test_reused_and_concurrent_graph_invocations_have_independent_profile_coordinators(monkeypatch):
    from contextvars import ContextVar
    invocation=ContextVar('profile_invocation');calls=[]
    stamps={label:(datetime.now(timezone.utc)-timedelta(seconds=index)).isoformat()
        for index,label in enumerate(('first','second'),1)}
    monkeypatch.setattr(daily,'publish_snapshot',lambda *args:None)
    monkeypatch.setattr(daily,'refresh_history',lambda *args:dict(status='complete'))
    async def collect(*args,**kwargs): return dict(status='complete',captured_at=stamps[invocation.get()],games=[])
    async def watch(*args,**kwargs):
        return dict(captured_at=stamps[invocation.get()],sources={'kalshi':dict(status='observed',partial_coverage=False)}),None
    async def profiles(sports,*,expected_public_captures):
        label=invocation.get();calls.append(label)
        assert expected_public_captures=={'nfl':dict(market_captured_at=stamps[label],slate_captured_at=stamps[label])}
        return {'nfl':profile_counts()}
    monkeypatch.setattr(daily,'collect_schedule',collect);monkeypatch.setattr(daily,'watch',watch)
    monkeypatch.setattr(daily,'refresh_profiles',profiles)
    graph=daily.create_daily_graph()
    async def invoke(label):
        token=invocation.set(label)
        try: return await graph.ainvoke(dict(sports=['nfl'],mode='public_daily',daily_credit_limit=20))
        finally: invocation.reset(token)
    first,second=await asyncio.gather(invoke('first'),invoke('second'))
    third=await invoke('first')
    assert calls.count('first')==2 and calls.count('second')==1
    coordinators=[state['profile_readiness']['nfl'] for state in (first,second,third)]
    assert len({id(value) for value in coordinators})==3
    assert [value.result() for value in coordinators]==[stamps['first'],stamps['second'],stamps['first']]


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['public_monitor','monitor','daily'])
async def test_profiles_are_not_requested_outside_public_daily(monkeypatch,mode):
    monkeypatch.setattr(daily,'publish_snapshot',lambda *args:None)
    monkeypatch.setattr(daily,'refresh_history',lambda *args:dict(status='complete'))
    monkeypatch.setattr(daily,'load_snapshot',lambda *args:dict(status='complete',finished_at=datetime.now(timezone.utc).isoformat()))
    monkeypatch.setattr(daily,'watch',AsyncMock(return_value=(dict(captured_at=datetime.now(timezone.utc).isoformat(),
        sources={'kalshi':dict(status='observed',partial_coverage=False)}),None)))
    monkeypatch.setattr(daily,'scan',AsyncMock(return_value={'nba':dict(status='complete')}))
    result=await daily.run(['nba'],mode,20)
    daily.refresh_profiles.assert_not_called()
    assert result['profiles']=={'nba':dict(status='not_requested',reason='public_daily_only')}
