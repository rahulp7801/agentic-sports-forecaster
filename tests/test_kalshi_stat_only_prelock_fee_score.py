"""Fee-aware paper costs require independent matching prelock receipts."""
import copy
from datetime import timedelta
from decimal import Decimal

import pytest

from sportsbet.market_watch import prop_fee_context
from sportsbet.quant import kalshi_stat_only_prelock_fee_score as score
from sportsbet.quant.kalshi_market_cohort import clock, digest
from tests.test_kalshi_exact_markout import market_for
from tests.test_kalshi_stat_only_prelock import fixture, observe
from tests.test_kalshi_stat_only_prelock_fees import checkpoint


def receipts(monkeypatch, *, fee_failure=False, quote_failure=False):
    market, forecast, decisions, kickoff, fee = checkpoint(
        monkeypatch, fail=fee_failure)
    pair, same_market, same_forecast, same_decisions, same_kickoff = fixture(monkeypatch)
    assert (market, forecast, decisions, kickoff) == (
        same_market, same_forecast, same_decisions, same_kickoff)
    quote = observe(market, forecast, decisions, kickoff,
                    None if quote_failure else market_for(pair, market))
    return market, forecast, decisions, kickoff, fee, quote


def test_exact_fee_and_quote_yield_hypothetical_full_group_cost(monkeypatch):
    market, forecast, decisions, _, fee, quote = receipts(monkeypatch)
    report = score.evaluate(market, forecast, decisions, fee, quote)
    assert report['frozen_candidates'] == report['frozen_games'] == 1
    assert report['candidate_states'] == {'one_contract_cost_modeled': 1}
    assert report['complete_cost_scenario'] is True
    assert Decimal(report['full_group_direct_total_cost']) > 0
    assert report['conditional_binary_direct_break_even_wins'] == 1
    assert report['actual_fills_verified'] is False
    assert report['venue_results_verified'] is False
    assert report['roi'] is None and report['edge_established'] is False


@pytest.mark.parametrize('fee_failure,quote_failure,expected', [
    (True, False, 'fee_unavailable'),
    (False, True, 'missing_exact_contract'),
])
def test_missing_evidence_stays_in_frozen_denominator(
        monkeypatch, fee_failure, quote_failure, expected):
    market, forecast, decisions, _, fee, quote = receipts(
        monkeypatch, fee_failure=fee_failure, quote_failure=quote_failure)
    report = score.evaluate(market, forecast, decisions, fee, quote)
    assert report['frozen_candidates'] == 1
    assert report['candidate_states'] == {expected: 1}
    assert report['complete_cost_scenario'] is False
    assert report['full_group_direct_total_cost'] is None
    assert report['conditional_binary_direct_break_even_wins'] is None


def test_fee_after_quote_and_active_waiver_do_not_create_cost(monkeypatch):
    market, forecast, decisions, kickoff, fee, quote = receipts(monkeypatch)
    late = copy.deepcopy(fee)
    event, item = next(iter(late['evidence']['sources'].items()))
    context = item['context']
    shifted = timedelta(seconds=1)
    received = context['received_at']
    later = clock(received) + shifted
    raw = item['raw']
    item['context'] = prop_fee_context(raw['series'], raw['series_changes'],
                                       event, raw['event_changes'], later)
    late['evidence']['captured_at'] = later.isoformat()
    late['evidence_sha256'] = digest(late['evidence'])
    report = score.evaluate(market, forecast, decisions, late, quote)
    assert report['candidate_states'] == {'fee_after_quote': 1}
    assert report['complete_cost_scenario'] is False
    waiver = copy.deepcopy(quote)
    waiver['evidence']['pages'][0]['body']['markets'][0][
        'fee_waiver_expiration_time'] = kickoff.isoformat()
    waiver['evidence_sha256'] = digest(waiver['evidence'])
    report = score.evaluate(market, forecast, decisions, fee, waiver)
    assert report['candidate_states'] == {'fee_waiver_unresolved': 1}
    waiver['evidence']['pages'][0]['body']['markets'][0][
        'fee_waiver_expiration_time'] = 'invalid'
    waiver['evidence_sha256'] = digest(waiver['evidence'])
    report = score.evaluate(market, forecast, decisions, fee, waiver)
    assert report['candidate_states'] == {'fee_waiver_unresolved': 1}


def test_individually_valid_receipts_over_five_minutes_apart_withhold_cost(monkeypatch):
    market, forecast, decisions, _, fee, quote = receipts(monkeypatch)
    stale_fee, later_quote = copy.deepcopy(fee), copy.deepcopy(quote)

    def shifted(value, delta):
        return (clock(value) + delta).isoformat()

    def shift_clock(proof, delta):
        proof['checked_at'] = shifted(proof['checked_at'], delta)
        for row in proof['observations']:
            for field in ('request_started_at', 'response_received_at', 'server_date'):
                row[field] = shifted(row[field], delta)

    earlier = -timedelta(minutes=2)
    evidence = stale_fee['evidence']
    for field in ('request_started_at', 'captured_at'):
        evidence[field] = shifted(evidence[field], earlier)
    shift_clock(evidence['clock_attestation'], earlier)
    event, source = next(iter(evidence['sources'].items()))
    raw = source['raw']
    raw['series']['last_updated_ts'] = shifted(raw['series']['last_updated_ts'], earlier)
    source['context'] = prop_fee_context(
        raw['series'], raw['series_changes'], event, raw['event_changes'],
        clock(source['context']['received_at']) + earlier)
    stale_fee['evidence_sha256'] = digest(evidence)

    later = timedelta(minutes=4)
    evidence = later_quote['evidence']
    evidence['captured_at'] = shifted(evidence['captured_at'], later)
    shift_clock(evidence['clock_attestation'], later)
    for page in evidence['pages']:
        for field in ('request_started_at', 'received_at'):
            page[field] = shifted(page[field], later)
    later_quote['evidence_sha256'] = digest(evidence)

    report = score.evaluate(market, forecast, decisions, stale_fee, later_quote)
    assert report['frozen_candidates'] == 1
    assert report['candidate_states'] == {'fee_changed_or_stale': 1}
    assert report['complete_cost_scenario'] is False
    assert report['full_group_direct_total_cost'] is None
    assert report['conditional_binary_direct_break_even_wins'] is None


def test_tampered_inputs_cannot_produce_cost(monkeypatch):
    market, forecast, decisions, _, fee, quote = receipts(monkeypatch)
    altered = copy.deepcopy(fee)
    next(iter(altered['evidence']['sources'].values()))['raw']['series'][
        'fee_multiplier'] = '0'
    altered['evidence_sha256'] = digest(altered['evidence'])
    with pytest.raises(ValueError, match='proof'):
        score.evaluate(market, forecast, decisions, altered, quote)
    changed = copy.deepcopy(quote)
    changed['evidence']['pages'][0]['body']['markets'][0]['floor_strike'] = '999.5'
    with pytest.raises(ValueError, match='commitment'):
        score.evaluate(market, forecast, decisions, fee, changed)
    with pytest.raises(ValueError, match='scope|kickoff group'):
        score.evaluate(market, forecast, decisions, fee,
                       dict(quote, evidence=dict(quote['evidence'],
                           kickoff='2026-10-06T00:15:00+00:00')))
