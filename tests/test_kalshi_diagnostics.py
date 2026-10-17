"""Diagnose existing failed reads without a second provider observation."""
from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from sportsbet import market_watch
from sportsbet.ingestion import kalshi


SECRET='MOCK_PRIVATE_PROVIDER_CONTENT'
NOW=datetime(2026,10,17,tzinfo=timezone.utc)


@pytest.mark.asyncio
@pytest.mark.parametrize('status,attempts',[(302,1),(401,1),(429,3),(503,3)])
async def test_read_error_keeps_runtime_compatibility_and_original_retry_bound(monkeypatch,status,attempts):
    calls=[]
    def handle(request):
        calls.append(request)
        return httpx.Response(status,json={'error':SECRET},headers={'Location':'https://secret.test/'+SECRET})
    sleep=AsyncMock();monkeypatch.setattr(kalshi.asyncio,'sleep',sleep)
    async with kalshi.KalshiReader(transport=httpx.MockTransport(handle)) as reader:
        with pytest.raises(RuntimeError,match=f'Kalshi read failed \\(HTTP {status}\\)') as caught:
            await reader._get('/markets',params={'cursor':SECRET})
    error=caught.value
    assert isinstance(error,kalshi.KalshiReadError)
    assert error.reason=='http_status' and error.http_status==status
    assert market_watch.kalshi_error_fields(error)==dict(
        error_type='KalshiReadError',reason='http_status',http_status=status)
    assert len(calls)==attempts and sleep.await_count==attempts-1
    assert all(request.method=='GET' and request.url.host=='external-api.kalshi.com' for request in calls)
    assert SECRET not in str(error) and 'https://' not in str(error)


@pytest.mark.asyncio
async def test_transport_diagnostics_never_copy_request_or_exception_text(monkeypatch):
    calls=[]
    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout(SECRET+' '+str(request.url),request=request)
    sleep=AsyncMock();monkeypatch.setattr(kalshi.asyncio,'sleep',sleep)
    async with kalshi.KalshiReader(transport=httpx.MockTransport(handle)) as reader:
        with pytest.raises(RuntimeError,match='Kalshi read failed \\(transport\\)') as caught:
            await reader._get('/markets',params={'cursor':SECRET})
    assert market_watch.kalshi_error_fields(caught.value)==dict(error_type='KalshiReadError',reason='transport')
    assert len(calls)==3 and sleep.await_count==2
    assert SECRET not in str(caught.value)


@pytest.mark.parametrize('reason,status',[('private',None),('transport',503),('http_status',None),
    ('http_status',True),('http_status','401'),('http_status',99),('http_status',600)])
def test_read_error_rejects_unbounded_or_invalid_diagnostic_fields(reason,status):
    with pytest.raises(ValueError,match='Invalid Kalshi read diagnostic'):
        kalshi.KalshiReadError(reason,status)


def test_failure_projection_does_not_trust_exception_attributes_or_message():
    error=RuntimeError(SECRET)
    error.reason='http_status';error.http_status=401
    assert market_watch.kalshi_error_fields(error)=={'error_type':'RuntimeError'}
    typed=kalshi.KalshiReadError('http_status',401)
    typed.reason=SECRET
    assert market_watch.kalshi_error_fields(typed)=={'error_type':'KalshiReadError'}
    typed.reason='http_status';typed.http_status=True
    assert market_watch.kalshi_error_fields(typed)=={'error_type':'KalshiReadError'}


@pytest.mark.parametrize('mutation,reason',[
    ('series','prop_series_mismatch'),('participant','prop_participant_mismatch'),
    ('team','prop_team_mismatch'),('strike','prop_strike_type_mismatch'),
    ('nan','invalid_prop_line'),('infinite','invalid_prop_line'),('negative','invalid_prop_line'),
    ('naive_start','invalid_prop_observation_window'),('naive_end','invalid_prop_observation_window'),
    ('reverse','invalid_prop_observation_window'),('hash','invalid_prop_page_commitment')])
def test_structured_prop_rejection_identifies_exact_predicate_without_provider_values(mutation,reason):
    value=dict(custom_strike=dict(football_player='30000000-0000-0000-0000-000000000003',
        football_team='10000000-0000-0000-0000-000000000001'),floor_strike=249.5,
        occurrence_datetime=NOW.isoformat(),primary_participant_key='football_player',strike_type='greater')
    game=dict(details=dict(league='NFL',home_team_id='10000000-0000-0000-0000-000000000001',
        away_team_id='20000000-0000-0000-0000-000000000002'))
    series='KXNFLPASSYDS';started=received=NOW;page_hash='a'*64
    if mutation=='series':series='KXNBAPTS'
    if mutation=='participant':value['primary_participant_key']=SECRET
    if mutation=='team':value['custom_strike']['football_team']='90000000-0000-0000-0000-000000000009'
    if mutation=='strike':value['strike_type']=SECRET
    if mutation=='nan':value['floor_strike']='NaN'
    if mutation=='infinite':value['floor_strike']='Infinity'
    if mutation=='negative':value['floor_strike']=-1
    if mutation=='naive_start':started=NOW.replace(tzinfo=None)
    if mutation=='naive_end':received=NOW.replace(tzinfo=None)
    if mutation=='reverse':started=NOW.replace(second=1)
    if mutation=='hash':page_hash=SECRET
    with pytest.raises(ValueError,match='^Invalid structured prop evidence$') as caught:
        market_watch.kalshi_prop_quote(value,series,'pass_yds',game,started,received,page_hash)
    fields=market_watch.kalshi_error_fields(caught.value)
    assert fields==dict(error_type='ValueError',reason=reason)
    assert SECRET not in json.dumps(fields) and SECRET not in str(caught.value)


def test_summary_counts_have_finite_categories_and_do_not_duplicate_prop_failures():
    failures=[dict(stage='prop_discovery',error_type='KalshiReadError',reason='http_status',http_status=401,
        series=SECRET,event_ticker=SECRET,player=SECRET,body=SECRET),
        dict(stage='prop_targets',error_type='ValueError',reason='invalid_structured_target_page'),
        dict(stage=SECRET,error_type=SECRET,reason=SECRET,http_status=SECRET),
        dict(stage='market',error_type='KalshiReadError',reason='http_status',http_status=True)]
    source=dict(failures=failures,prop_inventory=dict(failures=failures,
        fee_failures=[dict(stage='prop_fees',error_type='KalshiReadError',reason='transport')]))
    result=market_watch.kalshi_failure_counts(source)
    assert result==dict(total=5,by_stage=dict(prop_discovery=1,prop_targets=1,other=1,market=1,prop_fees=1),
        by_error_type=dict(KalshiReadError=3,ValueError=1,OtherError=1),
        by_reason=dict(http_status=2,invalid_structured_target_page=1,transport=1),by_http_status={'401':1})
    assert SECRET not in json.dumps(result)
    assert market_watch.kalshi_failure_counts({})==dict(
        total=0,by_stage={},by_error_type={},by_reason={},by_http_status={})
    many=[dict(stage=str(index),error_type=str(index),reason=str(index),http_status=index) for index in range(2000)]
    bounded=market_watch.kalshi_failure_counts({'failures':many})
    assert bounded==dict(total=2000,by_stage={'other':2000},by_error_type={'OtherError':2000},
        by_reason={},by_http_status={})


@pytest.mark.asyncio
async def test_original_reader_failure_reaches_logged_summary_without_new_requests(monkeypatch,tmp_path):
    client=httpx.AsyncClient;calls=[]
    def handle(request):
        calls.append(request)
        assert request.method=='GET'
        assert not any(name.upper().startswith('KALSHI-ACCESS-') for name in request.headers)
        path=request.url.path
        if path.endswith('/milestones'):
            return httpx.Response(200,json={'milestones':[],'cursor':''})
        if path.endswith('/markets'):
            assert request.url.params['series_ticker'] in market_watch.KALSHI_PROP_SERIES['nba']
            return httpx.Response(401,json={'error':SECRET})
        if path.endswith('/series/fee_changes'):
            return httpx.Response(200,json={'series_fee_change_arr':[]})
        if '/series/' in path:
            return httpx.Response(200,json={'series':{}})
        assert request.url.host=='site.api.espn.com'
        return httpx.Response(503)
    transport=httpx.MockTransport(handle)
    monkeypatch.setattr(httpx,'AsyncClient',lambda *args,**kwargs:client(*args,**(kwargs|{'transport':transport})))
    monkeypatch.chdir(tmp_path)
    report,path=await market_watch.run('nba',20,20,False,'kalshi')
    source=report['sources']['kalshi']
    assert source['status']=='degraded' and source['partial_coverage'] is True and source['count']==0
    assert source['coverage']['prop_series_observed']==0 and source['coverage']['prop_series_expected']==3
    assert source['coverage']['prop_discovery_complete'] is False
    assert source['failure_counts']==dict(total=3,by_stage={'prop_discovery':3},
        by_error_type={'KalshiReadError':3},by_reason={'http_status':3},by_http_status={'401':3})
    assert sum(request.url.path.endswith('/markets') for request in calls)==3
    assert report['comparisons']==[] and report['execution_ready'] is False
    assert SECRET not in json.dumps(report) and SECRET not in path.read_text()


@pytest.mark.asyncio
async def test_optional_fee_diagnostics_do_not_change_prop_coverage_or_drop_quotes():
    reader=AsyncMock()
    reader.series.side_effect=kalshi.KalshiReadError('http_status',503)
    reader.series_fee_changes.return_value={}
    contexts,failures=await market_watch.kalshi_prop_fee_contexts(reader,
        {'KXNBAPTS':'points'},{'KXNBAPTS-MOCK':{}})
    assert contexts=={} and failures==[dict(stage='prop_fees',series='KXNBAPTS',
        error_type='KalshiReadError',reason='http_status',http_status=503)]
    assert reader.series.await_count==reader.series_fee_changes.await_count==1
