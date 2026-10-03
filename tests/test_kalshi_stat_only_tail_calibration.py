"""Pre-result calibration stress test cannot rewrite the frozen October cohort."""
from datetime import datetime, timezone
import hashlib
import json

import pytest

from sportsbet.quant import kalshi_stat_only_tail_calibration as audit
from sportsbet.quant.kalshi_market_cohort import digest


def fixture(monkeypatch, states=None):
    bins = [dict(lower=.1, upper=.2, count=200, predicted=.15, observed=.20),
            dict(lower=.2, upper=.3, count=200, predicted=.25, observed=.27)]
    history = {'props': {prop: {'evaluation': {'selected': selected,
        'selection_scores': {selected: {'calibration_bins': bins}}}}
        for prop, selected in audit.SELECTED.items()}}
    forecast = {'forecasts': [
        dict(ticker='A', model_over_probability=.15, prop_type='rec_yds',
             scheduled_game_start_time='2026-10-04T13:30:00+00:00'),
        dict(ticker='B', model_over_probability=.25, prop_type='receptions',
             scheduled_game_start_time='2026-10-04T17:00:00+00:00')]}
    decisions = {'decided_at': '2026-10-04T00:30:00+00:00', 'candidates': [
        dict(ticker='A', side='no', milestone_id='G1', model_win_probability=.85),
        dict(ticker='B', side='no', milestone_id='G2', model_win_probability=.75)]}
    outcomes = states or {'A': ('venue_verified', 'no'), 'B': ('not_returned', None)}
    def primary(*args, **kwargs):
        base = dict(primary_protocol='frozen', original_market_contracts=3,
            primary_paper_candidates=3, paper_candidates=2, paper_games=2,
            selected_tickers_sha256=digest(['A','B']),
            first_eligible_settlement_at='2026-10-06T06:15:00+00:00')
        if args[-1] is not None:
            verified=[(key, result) for key,(state,result) in outcomes.items()
                      if state == 'venue_verified']
            base.update(verified_candidates=len(verified),
                verified_wins=sum(result == 'no' for _,result in verified),
                verified_games=len(verified),
                result_counts={state:sum(s == state for s,_ in outcomes.values())
                               for state,_ in outcomes.values()},
                settlement_evidence_sha256='synthetic')
        return base
    monkeypatch.setattr(audit.high, 'evaluate', primary)
    monkeypatch.setattr(audit.high, 'unpack', lambda pair: ({}, {}))
    monkeypatch.setattr(audit.high, 'venue_results', lambda *args, **kwargs: ([], outcomes))
    return history, forecast, decisions


def preflight(history, forecast, decisions):
    return audit.preflight({}, {}, forecast, {}, decisions, None, None, history)


def test_historical_selection_bins_shift_frozen_no_probabilities_without_reselecting(monkeypatch):
    history, forecast, decisions = fixture(monkeypatch)
    report, selected = preflight(history, forecast, decisions)
    assert report['paper_candidates'] == 2
    assert report['selected_tickers_sha256'] == digest(['A','B'])
    assert report['original_mean_model_win_probability'] == '0.80'
    assert report['corrected_mean_model_win_probability'] == '0.765'
    assert report['corrected_at_least_75_count'] == 1
    assert [str(row[2]) for row in selected] == ['0.80','0.73']
    assert report['result_counts'] is None and report['edge_established'] is False
    receipt = audit.freeze(report, decisions,
        now=datetime(2026,10,4,4,tzinfo=timezone.utc))
    assert receipt['record_sha256'] == digest({k:v for k,v in receipt.items()
                                              if k != 'record_sha256'})
    with pytest.raises(ValueError, match='before first kickoff'):
        audit.freeze(report, decisions, now=datetime(2026,10,4,13,30,tzinfo=timezone.utc))


def test_missing_venue_result_keeps_full_group_scores_null_and_receipt_is_bound(monkeypatch):
    history, forecast, decisions = fixture(monkeypatch)
    report, _ = preflight(history, forecast, decisions)
    receipt = audit.freeze(report, decisions, now=datetime(2026,10,4,4,tzinfo=timezone.utc))
    monkeypatch.setattr(audit, 'EXPECTED_RECORD_SHA256', receipt['record_sha256'])
    args = ({}, {}, forecast, {}, decisions, None, None, history, receipt,
            {'evidence_sha256':'synthetic'})
    result = audit.score(*args, now=datetime(2026,10,6,7,tzinfo=timezone.utc))
    assert result['verified_candidates'] == 1 and result['verified_games'] == 1
    assert result['pre_result_record_sha256'] == receipt['record_sha256']
    assert result['verified_subset_original_brier'] == '0.0225'
    assert result['verified_subset_corrected_brier'] == '0.0400'
    assert result['full_group_original_brier'] is None
    assert result['full_group_corrected_log_loss'] is None
    assert result['edge_established'] is False and result['qualified_picks'] == 0
    with pytest.raises(ValueError, match='receipt changed'):
        audit.score(*args[:8], {**receipt, 'corrected_mean_model_win_probability':'0.99'},
                    args[9], now=datetime(2026,10,6,7,tzinfo=timezone.utc))


def test_all_authenticated_results_score_same_fixed_group_without_edge_claim(monkeypatch):
    history, forecast, decisions = fixture(monkeypatch, {'A': ('venue_verified','no'),
                                                          'B': ('venue_verified','yes')})
    report, _ = preflight(history, forecast, decisions)
    receipt = audit.freeze(report, decisions, now=datetime(2026,10,4,4,tzinfo=timezone.utc))
    monkeypatch.setattr(audit, 'EXPECTED_RECORD_SHA256', receipt['record_sha256'])
    result = audit.score({}, {}, forecast, {}, decisions, None, None, history, receipt,
                         {'evidence_sha256':'synthetic'},
                         now=datetime(2026,10,6,7,tzinfo=timezone.utc))
    assert result['verified_candidates'] == 2
    assert result['full_group_original_brier'] is not None
    assert result['full_group_corrected_brier'] is not None
    assert result['edge_established'] is False


def test_wrong_side_bin_or_historical_hash_cannot_create_calibration(monkeypatch,tmp_path):
    history, forecast, decisions = fixture(monkeypatch)
    with pytest.raises(ValueError, match='NO identity'):
        preflight(history, forecast, {'decided_at':decisions['decided_at'],
            'candidates':[dict(decisions['candidates'][0],side='yes'),decisions['candidates'][1]]})
    with pytest.raises(ValueError, match='outside predeclared'):
        changed_forecast = {'forecasts':[dict(forecast['forecasts'][0],model_over_probability=.05),
            forecast['forecasts'][1]]}
        changed_decisions = {'decided_at': decisions['decided_at'], 'candidates': [
            dict(decisions['candidates'][0], model_win_probability=.95), decisions['candidates'][1]]}
        preflight(history, changed_forecast, changed_decisions)
    path=tmp_path/'history.json'
    path.write_text(json.dumps(history),encoding='utf-8')
    with pytest.raises(ValueError, match='commitment changed'):
        audit.pinned_history(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() != audit.HISTORY_SHA256
