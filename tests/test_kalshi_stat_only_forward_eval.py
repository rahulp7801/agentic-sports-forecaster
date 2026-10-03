"""Pre-result boundaries for the fixed October 4 NFL stat-only venue transfer."""
from datetime import datetime, timezone
from decimal import Decimal
import json

import pytest

from sportsbet.quant.kalshi_market_cohort import digest
from sportsbet.quant import kalshi_stat_only_forward_eval as audit


def test_pinned_receipt_rejects_changed_bytes(tmp_path):
    receipt = tmp_path / 'forecast.json'
    receipt.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='commitment changed'):
        audit._pinned(receipt, 'forecast')


def test_quote_after_decision_is_rejected_before_market_scoring():
    forecast = {'generated_at': '2026-10-04T00:00:01+00:00',
        'forecast_sha256': 'fixed', 'predicted_contracts': 1,
        'forecasts': [{'ticker': 'EXACT',
            'scheduled_game_start_time': '2026-10-04T17:00:00+00:00'}]}
    evidence = {'protocol': 'kalshi-nfl-stat-only-exact-quote-v1',
        'forecast_sha256': 'fixed', 'forecast_receipt_sha256': digest(forecast),
        'requested_tickers': ['EXACT'], 'captured_at': '2026-10-04T00:03:00+00:00',
        'pages': [{'tickers': ['EXACT'], 'request_started_at':
            '2026-10-04T00:02:00+00:00', 'received_at':
            '2026-10-04T00:03:00+00:00', 'body': {'markets': [], 'cursor': None}}]}
    quotes = {'evidence': evidence, 'evidence_sha256': digest(evidence)}
    with pytest.raises(ValueError, match='chronology'):
        audit._price_states({}, forecast, quotes,
            datetime.fromisoformat('2026-10-04T00:02:30+00:00'))


def test_missing_result_stays_in_denominator_and_full_profit_is_null():
    forecast = {'eligible_contracts': 3, 'forecasts': [
        {'ticker': 'A', 'milestone_id': 'GAME1', 'gsis_player_id': 'P1',
         'model_over_probability': .8, 'unfitted_prior_probability': .6,
         'snap_backed_zeros': 2},
        {'ticker': 'B', 'milestone_id': 'GAME2', 'gsis_player_id': 'P2',
         'model_over_probability': .7, 'unfitted_prior_probability': .5,
         'snap_backed_zeros': 0}]}
    decisions = {'candidates_count': 2, 'candidate_games': 2, 'candidates': [
        {'ticker': 'A', 'milestone_id': 'GAME1', 'side': 'yes', 'displayed_ask': '.4'},
        {'ticker': 'B', 'milestone_id': 'GAME2', 'side': 'no', 'displayed_ask': '.5'}]}
    prices = {'A': ('two_sided_exact', Decimal('.5'), {}, 'time'),
              'B': ('two_sided_exact', Decimal('.5'), {}, 'time')}
    states = {'A': ('venue_verified', 'yes'), 'B': ('not_returned', None)}
    report = audit.score_states(forecast, decisions, prices, states,
                                full_contracts=4, settlement_sha256='hash')
    assert report['forecast_result_counts'] == {'not_returned': 1, 'venue_verified': 1}
    assert report['candidate_result_counts'] == {'not_returned': 1, 'venue_verified': 1}
    assert report['two_sided_paired_results'] == 1
    assert report['verified_subset_gross_unit_profit'] == '0.6'
    assert report['full_cohort_gross_unit_profit'] is None
    zero=report['snap_backed_zero_sensitivity']['snap_backed_zero']
    no_zero=report['snap_backed_zero_sensitivity']['no_snap_backed_zero']
    assert (zero['forecast_contracts'],zero['paired_results'],zero['paper_candidates']) == (1,1,1)
    assert zero['paired_model_brier'] == '0.04'
    assert Decimal(zero['paired_model_log_loss']) > 0
    assert zero['verified_subset_win_rate'] == '1'
    assert zero['verified_subset_gross_unit_profit'] == '0.6'
    assert zero['full_bucket_gross_unit_profit'] == '0.6'
    assert (no_zero['forecast_contracts'],no_zero['paired_results'],no_zero['paper_candidates']) == (1,0,1)
    assert no_zero['verified_subset_gross_unit_profit'] is None
    assert no_zero['full_bucket_gross_unit_profit'] is None
    assert sum(group['forecast_contracts'] for group in
        report['snap_backed_zero_sensitivity'].values()) == report['model_forecasts']
    assert sum(group['paper_candidates'] for group in
        report['snap_backed_zero_sensitivity'].values()) == report['paper_candidates']
    assert report['probability_support'] is False
    assert report['edge_established'] is False
    assert report['qualified_picks'] == 0
    assert report['roi'] is None and report['clv'] is None


def test_settlement_audit_refuses_before_last_game_plus_six_hours(monkeypatch):
    called = False
    def fake_preflight(*args):
        return {'first_eligible_settlement_at': '2026-10-06T06:15:00+00:00'}, {}
    def forbidden_result(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError('venue results were read prematurely')
    monkeypatch.setattr(audit, 'preflight', fake_preflight)
    monkeypatch.setattr(audit, 'venue_results', forbidden_result)
    with pytest.raises(ValueError, match='premature'):
        audit.evaluate({}, {}, {}, {}, {}, None, None, {},
                       now=datetime.fromisoformat('2026-10-06T06:14:59+00:00'))
    assert not called


def test_postgame_path_preserves_full_original_market_denominator(monkeypatch):
    forecast = {'eligible_contracts': 1, 'forecasts': [
        {'ticker': 'A', 'milestone_id': 'GAME1', 'gsis_player_id': 'P1',
         'model_over_probability': .8, 'unfitted_prior_probability': .6,
         'snap_backed_zeros': 0}]}
    decisions = {'candidates_count': 1, 'candidate_games': 1, 'candidates': [
        {'ticker': 'A', 'milestone_id': 'GAME1', 'side': 'yes', 'displayed_ask': '.4'}]}
    prices = {'A': ('two_sided_exact', Decimal('.5'), {}, 'time')}
    def fake_preflight(*args):
        return {'first_eligible_settlement_at': '2026-10-06T06:15:00+00:00',
                'original_market_contracts': 2}, prices
    monkeypatch.setattr(audit, 'preflight', fake_preflight)
    monkeypatch.setattr(audit, 'unpack', lambda pair: ({'selections': []}, {}))
    monkeypatch.setattr(audit, 'venue_results', lambda *a, **k: (
        [{'ticker': 'A'}, {'ticker': 'B'}],
        {'A': ('venue_verified', 'yes'), 'B': ('not_returned', None)}))
    report = audit.evaluate({}, {}, forecast, {}, decisions, None, None,
        {'evidence_sha256': 'synthetic'},
        now=datetime.fromisoformat('2026-10-06T06:15:01+00:00'))
    assert report['full_venue_result_counts'] == {'not_returned': 1, 'venue_verified': 1}
    assert report['original_market_contracts'] == 2
    assert report['forecast_result_counts'] == {'venue_verified': 1}
    assert report['full_cohort_gross_unit_profit'] == '0.6'
    assert report['probability_support'] is False
    assert report['edge_established'] is False
    assert report['roi'] is None


def test_sensitivity_requires_frozen_nonnegative_integer_zero_count():
    forecast = {'eligible_contracts': 1, 'forecasts': [
        {'ticker': 'A', 'snap_backed_zeros': True}]}
    decisions = {'candidates_count': 0, 'candidate_games': 0, 'candidates': []}
    with pytest.raises(ValueError, match='snap-backed zero'):
        audit.score_states(forecast, decisions, {'A': ('missing', None, None, None)},
            {'A': ('not_returned', None)}, full_contracts=1,
            settlement_sha256='synthetic')
