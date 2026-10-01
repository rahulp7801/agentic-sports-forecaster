from copy import deepcopy
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from unittest.mock import AsyncMock,MagicMock,patch
import json

import pytest

from sportsbet.ingestion.provenance import stat_row_sha256
from sportsbet.quant import nfl_recent_role_shadow as source
from sportsbet.quant import nfl_rushing_role_shadow as rush
from sportsbet.quant.market_baseline import paired_market_baseline
from sportsbet.scan import quotes_from_event
from tests.test_nfl_recent_role_shadow import fixture as receiving_fixture


def fixture():
    payload,data=receiving_fixture('00-0037228','PIT')
    now=datetime.fromisoformat(rush.FROZEN_AT)+timedelta(minutes=1)
    observed=(now-timedelta(seconds=2)).isoformat()
    data.update(observed_at=(now-timedelta(seconds=1)).isoformat(),observed_before=observed,
                cutoff='2026-10-01')
    for index,item in enumerate(data['stats']):
        row=item['stat']
        row['rushing_yards']=80 if index%4==0 else 40
        row['source_record_sha256']=stat_row_sha256('nfl',row)
        row['source_observed_at']=observed
    for item in data['snaps']:
        item['snap']['source_observed_at']=observed
    event=dict(id='rush-shadow-test',home_team='Pittsburgh Steelers',away_team='Cleveland Browns',
        commence_time='2026-10-02T00:15:00Z',bookmakers=[dict(key='book',markets=[dict(
            key='player_rush_yds',last_update=observed,outcomes=[dict(name=side,point=73.5,
                price=-110,description=payload['player']) for side in ('Over','Under')])])])
    quotes=quotes_from_event(event,'nfl')
    quote=next(q for q in quotes if q.side=='Under')
    baseline=[item['stat'] for item in data['stats']]
    over=(sum(row['rushing_yards']>73.5 for row in baseline)+.5)/(len(baseline)+1)
    payload.update(game_id=event['id'],home_team=event['home_team'],away_team=event['away_team'],
        game_date=data['cutoff'],forecast_cutoff=data['cutoff'],game_start_time=event['commence_time'],
        prop_type='rush_yds',line=73.5,direction='under',model_sample_size=len(baseline),
        model_mean_stat=round(sum(row['rushing_yards'] for row in baseline)/len(baseline),2),
        model_probability=1-over,quote_time=observed,model_generated_at=now.isoformat(),
        captured_at=now.isoformat(),history_observed_before=observed,
        quote_source_provider=quote.source_provider,quote_source_sha256=quote.source_sha256,
        quote_source_record_sha256=quote.source_record_sha256,
        **paired_market_baseline(quote,quotes))
    payload['availability']['team']='PIT'
    payload['availability']['captured_at']=now.isoformat()
    return payload,data


def test_complete_pregame_offense_reweights_rushing_and_replays_exact_input():
    payload,data=fixture();before=deepcopy((payload,data))
    record=rush.shadow_record(payload,data)
    assert record['status']=='predicted',record
    assert record['counts']['sample_size']==33
    assert record['counts']['current_role_games']==3
    assert record['counts']['older_games']==30
    assert record['counts']['latest_game_gap_days']==4
    assert record['probability']!=payload['model_probability']
    assert rush.verified_shadow_probability(payload|{'rushing_role_shadow':record})==record['probability']
    assert (payload,data)==before
    changed=deepcopy(record);changed['probability']=.99
    assert rush.verified_shadow_probability(payload|{'rushing_role_shadow':changed}) is None


@pytest.mark.parametrize('fault,reason',[
    ('missing_snap','incomplete_participation_history'),
    ('late_stat','invalid_role_input'),
    ('wrong_baseline','baseline_history_mismatch'),
    ('stale_roster','invalid_current_roster'),
    ('different_team','latest_team_mismatch'),
    ('no_recent_team','no_current_role_history'),
    ('late_inputs','invalid_role_input'),
    ('wrong_line','unsupported_line'),
    ('changed_quote','invalid_exact_offer'),
])
def test_bad_or_late_inputs_do_not_produce_a_candidate(fault,reason):
    payload,data=fixture()
    if fault=='missing_snap': data['snaps'].pop()
    if fault=='late_stat': data['stats'][0]['stat']['source_observed_at']=payload['captured_at']
    if fault=='wrong_baseline': payload['model_mean_stat']+=1
    if fault=='stale_roster': payload['availability']['captured_at']='2026-09-29T00:00:00Z'
    if fault=='different_team': payload['availability']['team']='CLE'
    if fault=='no_recent_team':
        data['stats']=data['stats'][:-2];data['snaps']=data['snaps'][:-2]
        values=[item['stat']['rushing_yards'] for item in data['stats']]
        payload['model_sample_size']=len(values)
        payload['model_mean_stat']=round(sum(values)/len(values),2)
        payload['model_probability']=1-(sum(value>payload['line'] for value in values)+.5)/(len(values)+1)
    if fault=='late_inputs': data['observed_at']=(datetime.fromisoformat(payload['captured_at'])+timedelta(seconds=1)).isoformat()
    if fault=='wrong_line': payload['line']=74
    if fault=='changed_quote': payload['quote_source_record_sha256']='f'*64
    record=rush.shadow_record(payload,data)
    assert record['status']=='unavailable' and record['reason']==reason,record
    assert rush.verified_shadow_probability(payload|{'rushing_role_shadow':record}) is None


def test_existing_receiving_shadow_remains_unchanged():
    payload,data=fixture()
    baseline=source.shadow_record(payload,data)
    assert baseline['status']=='unavailable' and baseline['reason']=='unsupported_market'
    assert rush.shadow_record(payload,data)['status']=='predicted'


@pytest.mark.asyncio
async def test_scan_records_private_rushing_candidate_without_changing_public_pick(tmp_path,monkeypatch):
    from sportsbet import scan
    from sportsbet.config import settings
    from sportsbet.graph.models import PropResult
    from sportsbet.ledger import Ledger
    from sportsbet.quant import model_selection_paper as paper

    payload,data=fixture()
    now=datetime.fromisoformat(payload['captured_at'])
    data['observed_at']=data['observed_before']=now.isoformat()
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None): return now
    monkeypatch.setattr(scan,'datetime',Clock)
    monkeypatch.setattr('sportsbet.ledger.datetime',Clock)
    event=dict(id=payload['game_id'],home_team=payload['home_team'],away_team=payload['away_team'],
        commence_time=payload['game_start_time'],bookmakers=[dict(key='book',markets=[dict(
            key='player_rush_yds',last_update=payload['quote_time'],outcomes=[dict(name=side,
                point=payload['line'],price=-110,description=payload['player']) for side in ('Over','Under')])])])
    conn=MagicMock();conn.fetch=AsyncMock(return_value=[dict(normalized_name=payload['player'].lower(),player_id=payload['player_id'])])
    pool=MagicMock();pool.acquire.return_value.__aenter__=AsyncMock(return_value=conn)
    monkeypatch.setattr(scan,'write_player_prop_snapshots',AsyncMock())
    graph=MagicMock();graph.ainvoke=AsyncMock(return_value={'prop_result':PropResult(
        true_probability=Decimal(str(1-payload['model_probability'])),sample_size=payload['model_sample_size'],
        mean_stat=Decimal(str(payload['model_mean_stat'])),confidence_interval=(Decimal('.1'),Decimal('.5')))})
    monkeypatch.setattr(scan,'create_graph',lambda **kwargs:graph)
    monkeypatch.setattr(scan,'player_availability',lambda *args,**kwargs:(payload['availability']|{'subject_status':'Active'},None))
    monkeypatch.setattr(scan,'relevant_availability_reports',lambda *args:[])
    monkeypatch.setattr(scan,'historical_availability_splits',AsyncMock(return_value=[]))
    monkeypatch.setattr(scan,'load_ngs_evidence',AsyncMock(return_value=None))
    monkeypatch.setattr(settings,'history_shadow_enabled',False)
    monkeypatch.setattr(settings,'role_history_shadow_enabled',True)
    loader=AsyncMock(return_value={payload['player_id']:data})
    monkeypatch.setattr(source,'load_inputs',loader)
    ledger=Ledger(tmp_path/'rushing.sqlite',database_url='')
    result=await scan.evaluate_event(pool,event,'nfl',ledger,'rushing-prospective')
    loader.assert_awaited_once()
    assert loader.call_args.args[4]=={payload['player_id']}
    assert result['coverage']['rushing_role_shadow']['inference_counts']=={'predicted':2}
    assert len(result['signals'])==2
    assert all('rushing_role_shadow' not in signal for signal in result['signals'])
    forecasts=ledger.predictions()
    assert len(forecasts)==2
    assert all(rush.verified_shadow_probability(row) is not None for row in forecasts)
    assert all(row['role_history_shadow']['reason']=='unsupported_market' for row in forecasts)
    prepared=paper.prepare(forecasts,'nfl',now+timedelta(seconds=2))
    raw=[item for item in prepared if item['protocol']==paper.PROTOCOL['policies']['raw_model']]
    assert raw and all(any('rushing_role_shadow' in item for item in json.loads(receipt['payload'])['evidence']) for receipt in raw)


@pytest.mark.asyncio
async def test_rushing_only_read_failure_does_not_erase_receiving_history(tmp_path,monkeypatch):
    from sportsbet import scan
    from sportsbet.config import settings
    from sportsbet.graph.models import PropResult
    from sportsbet.ledger import Ledger

    running,rush_data=fixture()
    receiving,rec_data=receiving_fixture()
    now=datetime.fromisoformat(running['captured_at'])
    rec_data.update(observed_at=now.isoformat(),observed_before=now.isoformat(),cutoff=running['game_date'])
    receiving['availability']['captured_at']=now.isoformat()
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None): return now
    monkeypatch.setattr(scan,'datetime',Clock)
    monkeypatch.setattr('sportsbet.ledger.datetime',Clock)
    event=dict(id=running['game_id'],home_team=running['home_team'],away_team=running['away_team'],
        commence_time=running['game_start_time'],bookmakers=[dict(key='book',markets=[
            dict(key='player_rush_yds',last_update=running['quote_time'],outcomes=[dict(
                name=side,point=73.5,price=-110,description=running['player']) for side in ('Over','Under')]),
            dict(key='player_receptions',last_update=running['quote_time'],outcomes=[dict(
                name=side,point=.5,price=-110,description=receiving['player']) for side in ('Over','Under')])])])
    identities={running['player'].lower():running['player_id'],receiving['player'].lower():receiving['player_id']}
    conn=MagicMock();conn.fetch=AsyncMock(return_value=[dict(normalized_name=name,player_id=key)
        for name,key in identities.items()])
    pool=MagicMock();pool.acquire.return_value.__aenter__=AsyncMock(return_value=conn)
    monkeypatch.setattr(scan,'write_player_prop_snapshots',AsyncMock())
    async def model(state):
        if state['prop_type']=='rush_yds':
            return {'prop_result':PropResult(true_probability=Decimal(str(1-running['model_probability'])),
                sample_size=running['model_sample_size'],mean_stat=Decimal(str(running['model_mean_stat'])),
                confidence_interval=(Decimal('.1'),Decimal('.5')))}
        return {'prop_result':PropResult(true_probability=Decimal(str(receiving['model_probability'])),
            sample_size=receiving['model_sample_size'],mean_stat=Decimal(str(receiving['model_mean_stat'])),
            confidence_interval=(Decimal('.7'),Decimal('.99')))}
    graph=MagicMock();graph.ainvoke=AsyncMock(side_effect=model)
    monkeypatch.setattr(scan,'create_graph',lambda **kwargs:graph)
    by_name={running['player']:running['availability'],receiving['player']:receiving['availability']}
    monkeypatch.setattr(scan,'player_availability',lambda _,name,*args,**kwargs:(by_name[name]|{'subject_status':'Active'},None))
    monkeypatch.setattr(scan,'relevant_availability_reports',lambda *args:[])
    monkeypatch.setattr(scan,'historical_availability_splits',AsyncMock(return_value=[]))
    monkeypatch.setattr(scan,'load_ngs_evidence',AsyncMock(return_value=None))
    monkeypatch.setattr(settings,'history_shadow_enabled',False)
    monkeypatch.setattr(settings,'role_history_shadow_enabled',True)
    async def load(pool,sport,season,cutoff,requests,**kwargs):
        if requests=={running['player_id']}: raise RuntimeError('rushing-only read timed out')
        assert requests=={receiving['player_id']}
        return {receiving['player_id']:rec_data}
    loader=AsyncMock(side_effect=load)
    monkeypatch.setattr(source,'load_inputs',loader)
    ledger=Ledger(tmp_path/'isolated.sqlite',database_url='')
    result=await scan.evaluate_event(pool,event,'nfl',ledger,'isolated')
    assert loader.await_count==2
    assert {frozenset(call.args[4]) for call in loader.await_args_list}=={
        frozenset({running['player_id']}),frozenset({receiving['player_id']})}
    rows=ledger.predictions()
    assert len(rows)==4 and len(result['signals'])==4
    assert all(row['rushing_role_shadow']['reason']=='history_read_failed' for row in rows if row['prop_type']=='rush_yds')
    assert all(row['role_history_shadow'].get('reason')!='history_read_failed' for row in rows if row['prop_type']=='receptions')
