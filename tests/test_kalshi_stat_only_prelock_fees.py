"""Free fee checkpoint retains exact source proof and never requests quotes."""
import asyncio
import copy
from datetime import timedelta

import pytest

from sportsbet.quant import kalshi_stat_only_prelock_fees as fees
from sportsbet.quant.kalshi_market_cohort import clock, digest
from tests.test_kalshi_stat_only_prelock import fixture, observe


def checkpoint(monkeypatch, *, fail=False):
    _, market, forecast, decisions, kickoff = fixture(monkeypatch)
    original = market['evidence']['sources']['kalshi']['prop_inventory']['quotes'][0]
    proof = observe(market, forecast, decisions, kickoff)['evidence']['clock_attestation']
    at = kickoff - timedelta(minutes=75)

    class Reader:
        async def series(self, series):
            assert series == original['series_ticker']
            return {'ticker': series, 'fee_type': 'quadratic',
                    'fee_multiplier': '1',
                    'last_updated_ts': (at-timedelta(seconds=1)).isoformat()}

        async def series_fee_changes(self, series):
            assert series == original['series_ticker']
            return {'series_fee_change_arr': []}

        async def event_fee_changes(self, event):
            assert event == original['event_ticker']
            if fail:
                raise RuntimeError('fee endpoint unavailable')
            return {'event_fee_changes': [], 'cursor': ''}

        async def quoted_markets(self, *args):
            raise AssertionError('Fee checkpoint must not request quotes')

    receipt = asyncio.run(fees.capture(market, forecast, decisions, kickoff,
                                       Reader(), now=lambda: at,
                                       clock_proof=proof))
    return market, forecast, decisions, kickoff, receipt


def test_fee_checkpoint_records_public_terms_and_keeps_paper_scope(monkeypatch):
    market, forecast, decisions, _, receipt = checkpoint(monkeypatch)
    report = fees.evaluate(market, forecast, decisions, receipt)
    assert report['frozen_candidates'] == report['frozen_games'] == 1
    assert report['fee_events'] == 1
    assert report['fee_event_counts'] == {'observed': 1}
    assert report['quoted_prices_collected'] is False
    assert report['fee_adjusted_return'] is None
    assert report['edge_established'] is False
    assert report['qualified_picks'] == 0


def test_failed_fee_endpoint_keeps_event_unavailable(monkeypatch):
    market, forecast, decisions, _, receipt = checkpoint(monkeypatch, fail=True)
    report = fees.evaluate(market, forecast, decisions, receipt)
    assert report['fee_events'] == 1
    assert report['fee_event_counts'] == {'unavailable': 1}


def test_fee_checkpoint_rejects_later_mutations_even_with_recomputed_digest(monkeypatch):
    market, forecast, decisions, _, receipt = checkpoint(monkeypatch)
    changed = copy.deepcopy(receipt)
    source = next(iter(changed['evidence']['sources'].values()))
    source['raw']['series']['fee_multiplier'] = '0'
    changed['evidence_sha256'] = digest(changed['evidence'])
    with pytest.raises(ValueError, match='proof'):
        fees.evaluate(market, forecast, decisions, changed)
    altered = copy.deepcopy(decisions)
    altered['candidates'][0]['displayed_ask'] = '.01'
    with pytest.raises(ValueError, match='scope|identity'):
        fees.evaluate(market, forecast, altered, receipt)
    changed = copy.deepcopy(receipt)
    changed['evidence']['request_started_at'] = clock(changed['evidence']['kickoff']).isoformat()
    changed['evidence_sha256'] = digest(changed['evidence'])
    with pytest.raises(ValueError, match='scope|commitment'):
        fees.evaluate(market, forecast, decisions, changed)


def test_fee_checkpoint_rejects_out_of_window_before_network(monkeypatch):
    _, market, forecast, decisions, kickoff = fixture(monkeypatch)

    class Reader:
        async def series(self, *args):
            raise AssertionError('Late fee capture must not query provider')

    for at in (kickoff-timedelta(minutes=91), kickoff-timedelta(minutes=69)):
        with pytest.raises(ValueError, match='window'):
            asyncio.run(fees.capture(market, forecast, decisions, kickoff,
                                     Reader(), now=lambda: at))
