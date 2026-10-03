from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
import json

import pytest

from sportsbet.ledger import Ledger
from sportsbet.quant import nfl_corrected_workload_shadow as candidate
from sportsbet.quant import nfl_recent_role_shadow as role
from sportsbet.quant.nfl_corrected_workload_audit import report_corrected_workload
from sportsbet.quant.market_baseline import paired_market_baseline
from sportsbet.scan import quotes_from_event
from tests.test_nfl_recent_role_shadow import fixture as role_fixture


def fixture():
    payload, data = role_fixture()
    now = datetime(2026,10,3,17,1,tzinfo=timezone.utc)
    observed = (now-timedelta(seconds=2)).isoformat()
    start = now+timedelta(days=1)
    event = dict(id='corrected-workload-test',home_team='Home',away_team='Away',
        commence_time=start.isoformat(),bookmakers=[dict(key='book',markets=[dict(
            key='player_receptions',last_update=observed,outcomes=[dict(
                name=side,point=.5,price=-110,description=payload['player'])
                for side in ('Over','Under')])])])
    quotes = quotes_from_event(event,'nfl')
    quote = next(q for q in quotes if q.side=='Over')
    payload.update(game_id=event['id'],game_date=start.date().isoformat(),
        forecast_cutoff=start.date().isoformat(),game_start_time=start.isoformat(),
        quote_time=observed,captured_at=now.isoformat(),model_generated_at=now.isoformat(),
        sportsbook=quote.sportsbook,american_odds=quote.price,
        quote_source_provider=quote.source_provider,quote_source_sha256=quote.source_sha256,
        quote_source_record_sha256=quote.source_record_sha256,
        **paired_market_baseline(quote,quotes))
    payload['availability']['captured_at']=now.isoformat()
    data.update(cutoff=payload['game_date'],observed_before=observed,observed_at=observed)
    payload['history_observed_before']=observed
    role_record=role.shadow_record(payload,data)
    assert role_record['status']=='predicted',role_record
    payload['role_history_shadow']=role_record
    rows=[]
    for item in data['stats']:
        stat=item['stat']
        rows.append(dict(player=payload['player_id'],player_id=payload['player_id'],
            season=stat['season'],week=stat['week'],team=stat['team'],
            day=date.fromisoformat(item['game_date']),game=item['game_id'],
            passing_yards=stat['passing_yards'],rushing_yards=stat['rushing_yards'],
            receiving_yards=stat['receiving_yards'],receptions=stat['receptions'],
            targets=5,source_provider=stat['source_provider'],source_sha256=stat['source_sha256'],
            source_record_sha256=stat['source_record_sha256'],
            source_observed_at=stat['source_observed_at']))
    return payload,rows


def test_current_baseline_produces_replayable_untraded_shadow(tmp_path,monkeypatch):
    payload,rows=fixture()
    original=deepcopy((payload,rows))
    result=candidate.shadow_record(payload,rows)
    assert result['status']=='predicted',result
    assert (payload,rows)==original
    assert result['workload_source_commitment'] is False
    assert candidate.verified_shadow_probability(payload|{'history_shadow':result})==result['probability']
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime.fromisoformat(payload['captured_at'])+timedelta(seconds=1)
    monkeypatch.setattr('sportsbet.ledger.datetime',Clock)
    ledger=Ledger(tmp_path/'test.sqlite')
    ledger.record('scan',payload)
    recorded=ledger.predictions()[0]
    result=candidate.shadow_record(recorded,rows)
    recorded['history_shadow']=result
    recorded['history_shadow_recorded_at']=(datetime.fromisoformat(payload['captured_at'])+timedelta(seconds=2)).isoformat()
    assert candidate.verified_recorded_shadow_probability(recorded)==result['probability']
    assert report_corrected_workload([recorded|{'prediction_id':'one'}],'nfl')['markets']['receptions']['counts']['valid_predictions']==1
    assert recorded['accepted'] is False


@pytest.mark.parametrize(('change','reason'),[
    ('missing_target','missing_or_invalid_history'),
    ('wrong_stat','invalid_history_commitment'),
    ('missing_row','corrected_history_mismatch'),
    ('wrong_model','unsupported_baseline'),
    ('late_source','future_source_observation'),
    ('wrong_probability','role_receipt_unavailable'),
])
def test_mismatched_sources_and_baseline_abstain(change,reason):
    payload,rows=fixture()
    if change=='missing_target':rows[-1]['targets']=None
    elif change=='wrong_stat':rows[-1]['receptions']=7
    elif change=='missing_row':rows.pop()
    elif change=='wrong_model':payload['model_version']='empirical-jeffreys-v4'
    elif change=='late_source':rows[-1]['source_observed_at']=(datetime.fromisoformat(payload['captured_at'])+timedelta(seconds=1)).isoformat()
    else:payload['model_probability']=.5
    result=candidate.shadow_record(payload,rows)
    assert result['status']=='unavailable'
    assert result['reason']==reason


def test_receipt_tampering_and_missing_role_proof_fail(tmp_path,monkeypatch):
    payload,rows=fixture()
    result=candidate.shadow_record(payload,rows)
    tampered=deepcopy(result)
    tampered['probability']=.99
    assert candidate.verified_shadow_probability(payload|{'history_shadow':tampered}) is None
    assert candidate.shadow_record({k:v for k,v in payload.items() if k!='role_history_shadow'},rows)['reason']=='role_receipt_unavailable'
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime.fromisoformat(payload['captured_at'])+timedelta(seconds=1)
    monkeypatch.setattr('sportsbet.ledger.datetime',Clock)
    ledger=Ledger(tmp_path/'test.sqlite')
    ledger.record('scan',payload)
    recorded=ledger.predictions()[0]
    recorded['history_shadow']=candidate.shadow_record(recorded,rows)
    recorded['history_shadow_recorded_at']=(datetime.fromisoformat(payload['captured_at'])+timedelta(seconds=2)).isoformat()
    recorded['role_history_shadow_recorded_at']=recorded['game_start_time']
    assert candidate.verified_recorded_shadow_probability(recorded) is None


def test_audit_chooses_earliest_attempt_before_validity(tmp_path,monkeypatch):
    payload,rows=fixture()
    result=candidate.shadow_record(payload,rows)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime.fromisoformat(payload['captured_at'])+timedelta(seconds=1)
    monkeypatch.setattr('sportsbet.ledger.datetime',Clock)
    ledger=Ledger(tmp_path/'test.sqlite')
    ledger.record('scan',payload)
    valid=ledger.predictions()[0]|{'prediction_id':'z'}
    valid['history_shadow']=candidate.shadow_record(valid,rows)
    valid['history_shadow_recorded_at']=(datetime.fromisoformat(payload['captured_at'])+timedelta(seconds=2)).isoformat()
    unavailable=deepcopy(valid)
    unavailable['prediction_id']='a'
    unavailable['history_shadow']={'model_version':candidate.VERSION,'status':'unavailable',
        'reason':'corrected_history_mismatch'}
    report=report_corrected_workload([valid,unavailable],'nfl')
    counts=report['markets']['receptions']['counts']
    assert report['duplicate_attempts']==1
    assert counts['attempts']==1 and counts['unavailable']==1
    assert counts['valid_predictions']==0


def test_tampered_compressed_input_fails_closed():
    payload,rows=fixture()
    result=candidate.shadow_record(payload,rows)
    altered=deepcopy(result)
    altered['inputs']['data']='!!!'
    assert candidate.verified_shadow_probability(payload|{'history_shadow':altered}) is None
    changed=deepcopy(payload)
    changed['role_history_shadow']['probability']=.5
    assert candidate.verified_shadow_probability(changed|{'history_shadow':result}) is None
