"""A later unsigned exact quote must preserve the frozen candidate denominator."""
from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from sportsbet.quant import kalshi_exact_markout as markout
from sportsbet.quant.kalshi_market_cohort import digest
from tests.test_kalshi_fee_score import setup_pair
from tests.test_kalshi_role_shadow import RULES


LATER = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


def market_for(pair: dict, original: dict) -> dict:
    candidate = pair['ask_policy']['candidates'][0]
    old = original['evidence']['sources']['kalshi']['prop_inventory']['quotes'][0]
    selected = Decimal(candidate['displayed_ask']) + Decimal('.05')
    other = 1 - selected + Decimal('.04')
    yes, no = (selected, other) if candidate['side'] == 'yes' else (other, selected)
    return dict(ticker=old['ticker'], event_ticker=old['event_ticker'],
                status='active', strike_type=old['strike_type'],
                floor_strike=old['line'], primary_participant_key='football_player',
                custom_strike=dict(football_player=old['player_target_id'],
                                   football_team=old['team_target_id']),
                occurrence_datetime=old.get('market_occurrence_time',
                                            old['scheduled_game_start_time']),
                rules_primary=RULES['primary'],
                rules_secondary=RULES['secondary'],
                no_bid_dollars=str(1-yes), yes_ask_dollars=str(yes),
                yes_ask_size_fp='10.00', yes_bid_dollars=str(1-no),
                no_ask_dollars=str(no), yes_bid_size_fp='10.00')


def capture(pair: dict, original: dict, market: dict | None) -> dict:
    class Reader:
        async def quoted_markets(self, tickers):
            assert tickers == [pair['ask_policy']['candidates'][0]['ticker']]
            return {'markets': [market] if market is not None else [], 'cursor': ''}

    return asyncio.run(markout.collect(pair, original, Reader(), now=LATER,
                                       clock_now=lambda: LATER))


def test_later_exact_ask_is_source_bound_markout_not_a_return(monkeypatch):
    pair, original = setup_pair(monkeypatch)
    receipt = capture(pair, original, market_for(pair, original))
    for policy in ('role', 'prior20'):
        result = markout.evaluate(pair, original, receipt, policy=policy)
        assert result['frozen_candidates'] == result['prelock_matched_candidates'] == 1
        assert result['prelock_matched_games'] == 1
        assert result['full_candidate_state_counts'] == {'prelock_exact_ask': 1}
        assert result['complete_candidate_markout'] is True
        assert result['matched_subset_game_cluster_95'] is None
        assert Decimal(result['mean_side_ask_change']) == Decimal('.05')
        assert result['actual_fills_verified'] is False
        assert result['roi'] is None and result['edge_established'] is False


def test_missing_provider_result_and_changed_identity_remain_in_denominator(monkeypatch):
    pair, original = setup_pair(monkeypatch)
    missing = capture(pair, original, None)
    assert markout.evaluate(pair, original, missing)['full_candidate_state_counts'] == {
        'missing_exact_contract': 1}
    assert markout.evaluate(pair, original, missing)['complete_candidate_markout'] is False
    changed = capture(pair, original, market_for(pair, original))
    changed['evidence']['pages'][0]['body']['markets'][0]['floor_strike'] = '999.5'
    changed['evidence_sha256'] = digest(changed['evidence'])
    assert markout.evaluate(pair, original, changed)['full_candidate_state_counts'] == {
        'identity_changed': 1}
    tampered = copy.deepcopy(changed)
    tampered['evidence']['pages'][0]['body']['markets'][0]['floor_strike'] = '1.5'
    with pytest.raises(ValueError, match='integrity'):
        markout.evaluate(pair, original, tampered)


def test_unavailable_batch_bad_price_and_premature_capture_fail_closed(monkeypatch):
    pair, original = setup_pair(monkeypatch)
    class FailedReader:
        async def quoted_markets(self, tickers):
            raise RuntimeError('public read unavailable')
    unavailable = asyncio.run(markout.collect(pair, original, FailedReader(), now=LATER,
                                               clock_now=lambda: LATER))
    assert markout.evaluate(pair, original, unavailable)['full_candidate_state_counts'] == {
        'batch_unavailable': 1}
    bad = capture(pair, original, market_for(pair, original))
    bad['evidence']['pages'][0]['body']['markets'][0]['yes_ask_dollars'] = '0.01'
    bad['evidence_sha256'] = digest(bad['evidence'])
    assert markout.evaluate(pair, original, bad)['full_candidate_state_counts'] == {
        'invalid_quote': 1}
    with pytest.raises(ValueError, match='follow decision'):
        asyncio.run(markout.collect(pair, original, FailedReader(),
                                    now=datetime(2026, 10, 2, 18, 0, tzinfo=timezone.utc)))


def test_opposite_side_fractional_depth_does_not_discard_selected_ask(monkeypatch):
    pair, original = setup_pair(monkeypatch)
    candidate = pair['ask_policy']['candidates'][0]
    market = market_for(pair, original)
    opposite_size = 'yes_ask_size_fp' if candidate['side'] == 'no' else 'yes_bid_size_fp'
    selected_size = 'yes_bid_size_fp' if candidate['side'] == 'no' else 'yes_ask_size_fp'
    market[opposite_size] = '0.81'
    receipt = capture(pair, original, market)
    assert markout.evaluate(pair, original, receipt)['full_candidate_state_counts'] == {
        'prelock_exact_ask': 1}
    market[selected_size] = '0.81'
    receipt = capture(pair, original, market)
    assert markout.evaluate(pair, original, receipt)['full_candidate_state_counts'] == {
        'side_undersized': 1}


def test_extra_contract_and_reordered_scope_are_rejected(monkeypatch):
    pair, original = setup_pair(monkeypatch)
    receipt = capture(pair, original, market_for(pair, original))
    receipt['evidence']['pages'][0]['body']['markets'].append(dict(ticker='UNREQUESTED'))
    receipt['evidence_sha256'] = digest(receipt['evidence'])
    with pytest.raises(ValueError, match='Extra or duplicate'):
        markout.evaluate(pair, original, receipt)
    receipt = capture(pair, original, market_for(pair, original))
    receipt['evidence']['pages'][0]['tickers'] = ['UNREQUESTED']
    receipt['evidence_sha256'] = digest(receipt['evidence'])
    with pytest.raises(ValueError, match='chronology or scope'):
        markout.evaluate(pair, original, receipt)
