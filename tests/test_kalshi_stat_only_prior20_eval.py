"""Separate fixed-control scorer preserves missing outcomes and exact identities."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from sportsbet.quant import kalshi_stat_only_prior20_eval as control


def fixture():
    forecast = {'eligible_contracts': 2, 'forecasts': [
        {'ticker': 'A', 'milestone_id': 'GAME1', 'gsis_player_id': 'P1',
         'model_over_probability': .8, 'unfitted_prior_probability': .6,
         'snap_backed_zeros': 0},
        {'ticker': 'B', 'milestone_id': 'GAME2', 'gsis_player_id': 'P2',
         'model_over_probability': .7, 'unfitted_prior_probability': .5,
         'snap_backed_zeros': 0}]}
    decisions = {'candidates_count': 2, 'candidate_games': 2, 'candidates': [
        {'ticker': 'A', 'milestone_id': 'GAME1', 'side': 'yes', 'displayed_ask': '.4'},
        {'ticker': 'B', 'milestone_id': 'GAME2', 'side': 'no', 'displayed_ask': '.5'}]}
    receipt = {'protocol': 'kalshi-nfl-stat-only-fixed-prior20-control-v1',
               'original_forecasts': 2, 'forecast_rows': [
                   {'ticker': 'A', 'prior20_over_probability': .4},
                   {'ticker': 'B', 'prior20_over_probability': .6}]}
    prices = {'A': ('two_sided_exact', Decimal('.5'), {}, 'time'),
              'B': ('two_sided_exact', Decimal('.5'), {}, 'time')}
    states = {'A': ('venue_verified', 'yes'), 'B': ('not_returned', None),
              'OTHER': ('not_returned', None)}
    return forecast, decisions, receipt, prices, states


def test_strict_prior20_uses_same_verified_price_subset_and_fixed_denominators():
    forecast, decisions, receipt, prices, states = fixture()
    report = control.score_fixed(forecast, decisions, receipt, prices, states,
                                 full_contracts=3, settlement_sha256='original-result-hash')
    assert report['original_market_contracts'] == 3
    assert report['original_forecasts'] == report['forecast_result_counts']['venue_verified'] + report['forecast_result_counts']['not_returned'] == 2
    assert report['original_paper_decisions'] == 2
    assert report['same_price_paired_results'] == 1
    assert report['paired_model_brier'] == '0.04'
    assert report['paired_strict_prior20_brier'] == '0.36'
    assert report['original_comparator_actual'] == 'jeffreys_retained_20_to_40_games'
    assert report['all_selected_results_verified'] is False
    assert report['probability_support'] is False
    assert report['edge_established'] is False
    assert report['qualified_picks'] == 0
    assert report['roi'] is None


def test_strict_prior20_rejects_changed_ticker_or_missing_price():
    forecast, decisions, receipt, prices, states = fixture()
    receipt['forecast_rows'][0]['ticker'] = 'OTHER'
    with pytest.raises(ValueError, match='scope changed'):
        control.score_fixed(forecast, decisions, receipt, prices, states,
                            full_contracts=3, settlement_sha256='hash')
    receipt['forecast_rows'][0]['ticker'] = 'A'
    prices.pop('B')
    with pytest.raises(ValueError, match='scope changed'):
        control.score_fixed(forecast, decisions, receipt, prices, states,
                            full_contracts=3, settlement_sha256='hash')


def test_strict_prior20_rejects_nonbinary_verified_outcome():
    forecast, decisions, receipt, prices, states = fixture()
    states['A'] = ('venue_verified','void')
    with pytest.raises(ValueError,match='not binary'):
        control.score_fixed(forecast, decisions, receipt, prices, states,
                            full_contracts=3, settlement_sha256='hash')


def test_strict_prior20_gate_refuses_result_source_before_full_result_window(monkeypatch):
    monkeypatch.setattr(control,'preflight',lambda *args: (
        {'first_eligible_settlement_at':'2026-10-06T06:15:00+00:00'},{}))
    monkeypatch.setattr(control,'venue_results',lambda *args,**kwargs: (
        pytest.fail('Venue results read before fixed gate')))
    with pytest.raises(ValueError,match='premature'):
        control.evaluate({}, {}, {}, {}, {}, None, None,
                         Path('nonexistent-settlement-must-stay-unread.json'), None,
                         now=datetime(2026,10,6,6,14,59,tzinfo=timezone.utc))
