"""The six future quote attempts must never erase the fixed paper denominator."""
import copy
from datetime import timedelta
from decimal import Decimal

import pytest

from sportsbet.quant import kalshi_stat_only_prelock_series as series
from sportsbet.quant.kalshi_market_cohort import digest
from tests.test_kalshi_exact_markout import market_for
from tests.test_kalshi_stat_only_prelock import fixture, observe


def two_groups(monkeypatch):
    pair, original, forecast, decisions, first = fixture(monkeypatch)
    second = first+timedelta(hours=4)
    second_ticker = 'SECOND_EXACT'
    row = dict(forecast['forecasts'][0], ticker=second_ticker,
               scheduled_game_start_time=second.isoformat())
    forecast['forecasts'].append(row)
    forecast['forecast_sha256'] = digest(forecast['forecasts'])
    candidate = dict(decisions['candidates'][0], ticker=second_ticker,
                     milestone_id='SECOND_GAME')
    decisions['candidates'].append(candidate)
    decisions['candidates_count'] = 2
    decisions['candidates_sha256'] = digest(decisions['candidates'])
    decisions['model_forecast_sha256'] = forecast['forecast_sha256']
    old = copy.deepcopy(original['evidence']['sources']['kalshi']['prop_inventory']['quotes'][0])
    old.update(ticker=second_ticker,scheduled_game_start_time=second.isoformat(),
               market_occurrence_time=second.isoformat())
    original['evidence']['sources']['kalshi']['prop_inventory']['quotes'].append(old)
    first_market = market_for(pair, original)
    second_market = dict(first_market,ticker=second_ticker,
                         occurrence_datetime=second.isoformat())
    return original, forecast, decisions, first, second, first_market, second_market


def test_pending_then_missing_capture_retains_both_fixed_candidates(monkeypatch):
    original, forecast, decisions, first, second, first_market, _ = two_groups(monkeypatch)
    first_receipt = observe(original, forecast, decisions, first, first_market)
    report = series.evaluate(original, forecast, decisions, [first_receipt],
        now=first-timedelta(minutes=70))
    assert report['frozen_candidates'] == 2
    assert report['observed_kickoff_groups'] == 1
    assert report['full_candidate_state_counts'] == {'not_yet_due': 1, 'prelock_exact_ask': 1}
    assert report['matched_candidates'] == 1
    assert report['complete_markout'] is False
    assert report['mean_side_ask_change'] == '0.05'
    assert report['edge_established'] is False and report['roi'] is None
    late = series.evaluate(original, forecast, decisions, [first_receipt],
        now=second-timedelta(minutes=69))
    assert late['full_candidate_state_counts'] == {'missed_capture': 1, 'prelock_exact_ask': 1}
    assert late['complete_markout'] is False


def test_complete_two_group_replay_and_duplicate_capture_rejected(monkeypatch):
    original, forecast, decisions, first, second, first_market, second_market = two_groups(monkeypatch)
    first_receipt = observe(original, forecast, decisions, first, first_market)
    second_receipt = observe(original, forecast, decisions, second, second_market)
    report = series.evaluate(original, forecast, decisions,
        [second_receipt, first_receipt], now=second-timedelta(minutes=70))
    assert report['frozen_candidates'] == report['matched_candidates'] == 2
    assert report['observed_kickoff_groups'] == 2
    assert report['complete_markout'] is True
    assert report['full_candidate_state_counts'] == {'prelock_exact_ask': 2}
    assert Decimal(report['equal_game_mean_side_ask_change']) == Decimal('.05')
    assert report['closing_line_verified'] is False and report['clv'] is None
    with pytest.raises(ValueError, match='duplicate'):
        series.evaluate(original, forecast, decisions,
            [first_receipt, first_receipt], now=second)
    with pytest.raises(ValueError, match='after audit'):
        series.evaluate(original, forecast, decisions,
            [second_receipt], now=first)
