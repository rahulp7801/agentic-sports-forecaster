"""Real scalar scorer regression; reporting repairs cannot relax frozen gates."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import math
from pathlib import Path

import pytest

from sportsbet.quant import kalshi_stat_only_next_eval as frozen
from sportsbet.quant import kalshi_stat_only_next_eval_v2 as repaired
from sportsbet.quant.kalshi_market_cohort import digest


@pytest.fixture
def case(monkeypatch):
    now = datetime(2026, 10, 13, 8, tzinfo=timezone.utc)
    rows = [dict(ticker=name, milestone_id='game-'+name, gsis_player_id='player-'+name,
                 snap_backed_zeros=index % 2, model_over_probability='.5',
                 unfitted_prior_probability=prior)
            for index, (name, prior) in enumerate([('a','.2'),('b','.8'),('c','.1'),('d','.9')])]
    values = dict(pair={}, market={}, forecast=dict(forecasts=rows, eligible_contracts=4),
                  decisions=dict(candidates=[], candidates_count=0, candidate_games=0),
                  control=dict(forecast_rows=[dict(ticker=row['ticker'],
                               prior20_over_probability='.6' if row['ticker']=='a' else '.4')
                               for row in rows]))
    states = dict(a=('venue_verified','yes'),b=('venue_verified','no'),
                  c=('nonbinary_result',None),d=('venue_verified','yes'))
    prices = {name: ('two_sided_exact',Decimal('.5'),None,None) for name in states}
    prices['d'] = ('missing_quote',None,None,None)
    pre = dict(first_eligible_settlement_at=(now-timedelta(hours=1)).isoformat(),
               original_market_contracts=4)
    commitment = {'original':'unchanged'}
    receipt = dict(protocol=frozen.SETTLEMENT_VERSION,
                   pregame_commitment_sha256=digest(commitment),
                   clock_proof={}, captured_at=now.isoformat(), evidence_sha256='a'*64)
    receipt['record_sha256'] = digest(receipt)
    for module in (frozen,repaired):
        monkeypatch.setattr(module,'committed_preflight',lambda *args:(values,pre,prices))
        monkeypatch.setattr(module,'unpack',lambda *args:({},{}))
        monkeypatch.setattr(module,'venue_results',lambda *args,**kwargs:([1,2,3,4],states))
    from sportsbet.quant import kalshi_stat_only_settlement_capture as clock_module
    monkeypatch.setattr(clock_module,'validate_clock_proof',lambda *args:None)
    monkeypatch.setattr(repaired,'validate_clock_proof',lambda *args:None)
    return now,values,prices,states,commitment,receipt


def test_original_failure_is_preserved_and_repair_uses_exact_paired_rows(case):
    now,values,prices,states,commitment,receipt=case
    original=deepcopy((values,prices,states,commitment,receipt))
    with pytest.raises(KeyError,match='paired_prior_log_loss'):
        frozen.evaluate({},Path('.'),commitment,receipt,now=now)
    report=repaired.evaluate({},Path('.'),commitment,receipt,now=now)
    assert report['protocol']==repaired.VERSION!=frozen.VERSION
    assert report['two_sided_paired_results']==2
    assert float(report['paired_retained_history_log_loss'])==pytest.approx(-math.log(.2))
    assert float(report['paired_strict_prior20_log_loss'])==pytest.approx(-math.log(.6))
    assert report['paired_retained_history_brier']=='0.64'
    assert report['paired_model_brier']=='0.25'
    assert report['paired_market_brier']=='0.25'
    assert report['full_venue_result_counts']=={'nonbinary_result':1,'venue_verified':3}
    assert report['probability_support'] is False
    assert report['edge_established'] is False and report['qualified_picks']==0
    assert report['roi'] is None and report['execution_ready'] is False
    assert len(report['evaluation_implementation_sha256'])==64
    assert (values,prices,states,commitment,receipt)==original


def test_missing_pairs_remain_unavailable(case):
    now,values,prices,states,commitment,receipt=case
    states.update({name:('nonbinary_result',None) for name in states})
    report=repaired.evaluate({},Path('.'),commitment,receipt,now=now)
    assert report['two_sided_paired_results']==0
    assert report['paired_retained_history_log_loss'] is None
    assert report['paired_retained_history_brier'] is None
    assert report['probability_support'] is False


@pytest.mark.parametrize('failure',['premature','tampered_result','failed_source'])
def test_original_gate_failure_precedes_any_result_scoring(case,monkeypatch,failure):
    now,_,_,_,commitment,receipt=case
    monkeypatch.setattr(repaired,'venue_results',lambda *args,**kwargs:pytest.fail('Venue scoring after failed gate'))
    if failure=='premature': now-=timedelta(hours=2)
    elif failure=='tampered_result': receipt['captured_at']='2030-01-01T00:00:00Z'
    else:
        def reject(*args): raise ValueError('Pregame source changed')
        monkeypatch.setattr(repaired,'committed_preflight',reject)
    with pytest.raises(ValueError):
        repaired.evaluate({},Path('.'),commitment,receipt,now=now)


def test_scalar_repair_refuses_a_changed_pair_denominator(case):
    _,values,prices,states,_,_=case
    with pytest.raises(ValueError,match='denominator changed'):
        repaired.retained_history_log_loss(values['forecast'],prices,states,3)


def test_report_forks_keep_original_pregame_bindings_and_policy():
    from sportsbet.quant import kalshi_stat_only_next_series_v2 as old_series
    from sportsbet.quant import kalshi_stat_only_next_series_v3 as series
    from sportsbet.quant import kalshi_stat_only_next_teammate_study_v2 as old_study
    from sportsbet.quant import kalshi_stat_only_next_teammate_study_v3 as study
    assert old_series.single is frozen and series.single is repaired
    assert old_study.single is frozen and study.single is repaired
    assert study.VERSION==old_study.VERSION
    assert study.MARKER_VERSION==old_study.MARKER_VERSION
    assert study.POLICY==old_study.POLICY and study.FILES==old_study.FILES
    assert study.implementation()==old_study.implementation()
    assert study.EVALUATION_VERSION!=old_study.VERSION
    assert series.HIGH_PROBABILITY==old_series.HIGH_PROBABILITY
