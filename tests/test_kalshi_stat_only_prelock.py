"""A later free quote can only measure the fixed candidate at its exact kickoff."""
import asyncio
import copy
from datetime import timedelta
from decimal import Decimal

import pytest

from sportsbet.quant import kalshi_stat_only_prelock as prelock
from sportsbet.quant.clock_attestation import HOSTS, VERSION as CLOCK_VERSION
from sportsbet.quant.kalshi_market_cohort import clock, digest
from tests.test_kalshi_exact_markout import market_for
from tests.test_kalshi_fee_score import setup_pair


def fixture(monkeypatch):
    pair, original = setup_pair(monkeypatch)
    candidate = pair['ask_policy']['candidates'][0]
    old = original['evidence']['sources']['kalshi']['prop_inventory']['quotes'][0]
    kickoff = clock(old['scheduled_game_start_time'])
    rows = [dict(ticker=candidate['ticker'], scheduled_game_start_time=kickoff.isoformat())]
    forecast = dict(forecasts=rows, forecast_sha256=digest(rows))
    decisions = dict(candidates=[candidate], candidates_count=1,
        candidates_sha256=digest([candidate]), model_forecast_sha256=forecast['forecast_sha256'],
        decided_at=pair['ask_policy']['frozen_at'])
    return pair, original, forecast, decisions, kickoff


def observe(original, forecast, decisions, kickoff, market=None, fail=False):
    class Reader:
        async def quoted_markets(self, tickers):
            assert len(tickers) == 1
            if fail:
                raise RuntimeError('public quote unavailable')
            return dict(markets=[] if market is None else [market], cursor='')
    at = kickoff-timedelta(minutes=75)
    started=at-timedelta(seconds=2)
    received=at-timedelta(seconds=1)
    proof=dict(protocol=CLOCK_VERSION, checked_at=received.isoformat(),
        local_clock_acceptable=True, observations=[dict(host=host,
            request_started_at=started.isoformat(),response_received_at=received.isoformat(),
            server_date=(started+timedelta(milliseconds=500)).isoformat(),
            rtt_seconds=1,server_minus_local_seconds=0,age=None,http_status=200)
            for host in HOSTS])
    return asyncio.run(prelock.capture(original, forecast, decisions, kickoff, Reader(),
                                      now=lambda: at, clock_proof=proof))


def test_later_exact_ask_movement_is_unfilled_and_preserves_denominator(monkeypatch):
    pair, original, forecast, decisions, kickoff = fixture(monkeypatch)
    receipt = observe(original, forecast, decisions, kickoff, market_for(pair, original))
    report = prelock.evaluate(original, forecast, decisions, receipt)
    assert report['frozen_candidates'] == report['matched_candidates'] == 1
    assert report['candidate_state_counts'] == {'prelock_exact_ask': 1}
    assert Decimal(report['mean_side_ask_change']) == Decimal('.05')
    assert report['complete_markout'] is True
    assert report['actual_fills_verified'] is False
    assert report['closing_line_verified'] is False
    assert report['roi'] is None and report['clv'] is None
    assert report['edge_established'] is False and report['qualified_picks'] == 0


def test_missing_failed_and_changed_exact_quote_remain_in_fixed_group(monkeypatch):
    pair, original, forecast, decisions, kickoff = fixture(monkeypatch)
    assert prelock.evaluate(original, forecast, decisions,
        observe(original, forecast, decisions, kickoff))['candidate_state_counts'] == {'missing_exact_contract': 1}
    assert prelock.evaluate(original, forecast, decisions,
        observe(original, forecast, decisions, kickoff, fail=True))['candidate_state_counts'] == {'batch_unavailable': 1}
    changed = market_for(pair, original)
    changed['floor_strike'] = '999.5'
    assert prelock.evaluate(original, forecast, decisions,
        observe(original, forecast, decisions, kickoff, changed))['candidate_state_counts'] == {'identity_changed': 1}


def test_window_and_receipt_commitment_reject_late_or_mutated_price(monkeypatch):
    pair, original, forecast, decisions, kickoff = fixture(monkeypatch)
    class Reader:
        async def quoted_markets(self, tickers):
            raise AssertionError('late capture must not query provider')
    for at in (kickoff-timedelta(minutes=91), kickoff-timedelta(minutes=69)):
        with pytest.raises(ValueError, match='window'):
            asyncio.run(prelock.capture(original, forecast, decisions, kickoff, Reader(), now=lambda: at))
    receipt = observe(original, forecast, decisions, kickoff, market_for(pair, original))
    changed = copy.deepcopy(receipt)
    changed['evidence']['pages'][0]['body']['markets'][0]['floor_strike'] = '999.5'
    with pytest.raises(ValueError, match='commitment'):
        prelock.evaluate(original, forecast, decisions, changed)
    altered = copy.deepcopy(decisions)
    altered['candidates'][0]['displayed_ask'] = '.01'
    with pytest.raises(ValueError, match='scope'):
        prelock.evaluate(original, forecast, altered, receipt)
    changed_original = copy.deepcopy(original)
    changed_original['summary']['evidence_sha256'] = 'changed'
    with pytest.raises(ValueError, match='commitment'):
        prelock.evaluate(changed_original, forecast, decisions, receipt)
    false_clock = copy.deepcopy(receipt)
    false_clock['evidence']['clock_attestation']['observations'][0]['age'] = '30'
    false_clock['evidence_sha256'] = digest(false_clock['evidence'])
    with pytest.raises(ValueError, match='clock response'):
        prelock.evaluate(original, forecast, decisions, false_clock)
    stale_clock = copy.deepcopy(receipt)
    proof = stale_clock['evidence']['clock_attestation']
    proof['checked_at'] = (clock(proof['checked_at'])-timedelta(seconds=121)).isoformat()
    for observation in proof['observations']:
        for key in ('request_started_at', 'response_received_at', 'server_date'):
            observation[key] = (clock(observation[key])-timedelta(seconds=121)).isoformat()
    stale_clock['evidence_sha256'] = digest(stale_clock['evidence'])
    with pytest.raises(ValueError, match='clock proof chronology'):
        prelock.evaluate(original, forecast, decisions, stale_clock)
    for field,value in [('rtt_seconds', True), ('server_minus_local_seconds', False),
                        ('age', False)]:
        false_clock = copy.deepcopy(receipt)
        false_clock['evidence']['clock_attestation']['observations'][0][field] = value
        false_clock['evidence_sha256'] = digest(false_clock['evidence'])
        with pytest.raises(ValueError, match='clock response'):
            prelock.evaluate(original, forecast, decisions, false_clock)
