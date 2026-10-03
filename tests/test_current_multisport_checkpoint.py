from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace
import sys
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from sportsbet.ledger import Ledger
from sportsbet.quant import current_multisport_checkpoint as checkpoint


def result(sport):
    protocol = checkpoint.EVALUATORS[sport].PROTOCOL
    return {
        'protocol': dict(protocol),
        'protocol_sha256': hashlib.sha256(json.dumps(protocol, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest(),
        'evaluator_sha256': checkpoint.EVALUATORS[sport].source_digests(),
        'sport': sport, 'observed_at': datetime(2026, 10, 3, tzinfo=timezone.utc).isoformat(),
        'status': 'insufficient_data', 'assessment': {'status': 'insufficient_data'},
        'cohorts': {'all_predictions': {'paired_games': 0},
                    'recommendations': {'decided': 0}},
        'promote': False,
        'scope': 'Separate sport evidence; hypothetical recorded prices, no executed profit.',
    }


@pytest.mark.parametrize('sport,version', [('nba', 'nba-cfb-priced-prospective-v1'),
    ('cfb', 'cfb-history-priced-prospective-v1')])
def test_each_current_sport_keeps_its_frozen_protocol_and_private_hash(sport, version):
    assert checkpoint.frozen_source_digests(sport) == checkpoint.FROZEN_DIGESTS[sport]
    retained = checkpoint.build_report(result(sport), sport)
    assert retained['protocol']['version'] == version
    assert retained['target_verified'] is False
    observed, payload, digest = checkpoint.encode_report(retained, sport)
    assert observed == datetime(2026, 10, 3, tzinfo=timezone.utc)
    assert digest == hashlib.sha256(payload.encode()).hexdigest()
    assert 'player_id' not in payload and 'prediction_id' not in payload


@pytest.mark.parametrize('sport', ['nba', 'cfb'])
def test_private_retention_rejects_changed_sport_policy_or_evaluator(sport, monkeypatch):
    original = result(sport)
    other = 'cfb' if sport == 'nba' else 'nba'
    for changed in [original | {'sport': other}, original | {'promote': True},
        original | {'protocol': checkpoint.EVALUATORS[other].PROTOCOL},
        original | {'evaluator_sha256': {}}, original | {'status': 'supported'},
        original | {'cohorts': {'recommendations': {}}},
        original | {'observed_at': '2026-09-24T00:00:00+00:00'},
        original | {'observed_at': '2026-10-03T00:00:00'}]:
        with pytest.raises((ValueError, TypeError)):
            checkpoint.build_report(changed, sport)
    changed = checkpoint.FROZEN_DIGESTS[sport] | {'runner': '0'*64}
    monkeypatch.setitem(checkpoint.FROZEN_DIGESTS, sport, changed)
    with pytest.raises(ValueError, match='new protocol required'):
        checkpoint.build_report(original, sport)


def test_private_retention_refuses_raw_rows_nonfinite_or_forged_promotion(monkeypatch):
    report = checkpoint.build_report(result('cfb'), 'cfb')
    report['target_verified'] = True
    with pytest.raises(ValueError):
        checkpoint.encode_report(report, 'cfb')
    report['target_verified'] = False
    report['cohorts']['recommendations']['bad'] = float('nan')
    with pytest.raises(ValueError):
        checkpoint.encode_report(report, 'cfb')
    calls=[]
    monkeypatch.setattr(checkpoint, 'insert_report', lambda *args:calls.append(args))
    report=checkpoint.build_report(result('nba'),'nba')
    checkpoint.store_report('postgresql://unused',report,'nba')
    assert len(calls)==1 and calls[0][1]=='nba-cfb-priced-prospective-v1'
    assert len(calls[0][-1])==64


@pytest.mark.parametrize('sport', ['nba', 'cfb'])
def test_real_empty_ledger_audit_is_aggregate_and_retained(sport, tmp_path):
    evaluator=checkpoint.EVALUATORS[sport]
    ledger=Ledger(tmp_path/'audit.sqlite')
    audited=evaluator.audit_sport(ledger,sport,now=datetime(2026,10,3,tzinfo=timezone.utc))
    report=checkpoint.build_report(audited,sport)
    assert report['status']=='insufficient_data'
    assert report['cohorts']['all_predictions']['source_eligible']==0
    checkpoint.encode_report(report,sport)


def test_private_report_refuses_nested_player_rows():
    for detail in ({'player_id': '123'}, [{'player': 'Private athlete'}],
                   {'nested': [{'game_id': '123'}]}):
        unsafe=result('nba')
        unsafe['cohorts']['recommendations']['detail']=detail
        with pytest.raises(ValueError, match='row-level'):
            checkpoint.build_report(unsafe, 'nba')


def test_all_sport_audit_keeps_cfb_attempt_after_nba_failure(monkeypatch, capsys):
    stored=[]
    def failing(*args, **kwargs):
        raise ValueError('private detail must not appear in logs')
    def working(*args, **kwargs):
        return {'status':'insufficient_data'}
    ledger=lambda **kwargs:SimpleNamespace(snapshot=lambda:nullcontext())
    monkeypatch.setattr(checkpoint, 'EVALUATORS', {
        'nba':SimpleNamespace(ProspectiveLedger=ledger,audit_sport=failing,
            PROTOCOL={'version':'nba-cfb-priced-prospective-v1'}),
        'cfb':SimpleNamespace(ProspectiveLedger=ledger,audit_sport=working,
            PROTOCOL={'version':'cfb-history-priced-prospective-v1'})})
    monkeypatch.setattr(checkpoint, 'audit_database_url',lambda:'postgresql://unused')
    monkeypatch.setattr(checkpoint, 'build_report',lambda result,sport:result)
    monkeypatch.setattr(checkpoint, 'store_report',lambda url,result,sport:stored.append(sport))
    monkeypatch.setattr(sys, 'argv', ['checkpoint', '--sport', 'all'])
    with pytest.raises(SystemExit, match='incomplete: nba'):
        checkpoint.main()
    assert stored==['cfb']
    printed=capsys.readouterr().out
    assert 'private detail' not in printed
    assert '"sport": "nba"' in printed and '"sport": "cfb"' in printed


def test_existing_daily_job_runs_the_restricted_multisport_audit_without_new_schedule():
    workflow=yaml.safe_load((Path(__file__).parents[1]/'.github/workflows/data.yml').read_text())
    steps=workflow['jobs']['update']['steps']
    matches=[step for step in steps if step.get('name')=='Retain current NBA and CFB priced evidence privately']
    assert len(matches)==1
    step=matches[0]
    assert "env.OPERATION == 'daily'" in step['if']
    assert 'current_multisport_checkpoint --sport "$audit_sport"' in step['run']
    assert 'ODDS_API_KEY' not in step.get('env',{})
    assert 'ANALYTICS_DATABASE_URL' in step['env']
