"""The 70-row fee/quote rollup keeps absent groups in the fixed denominator."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sportsbet.quant import kalshi_stat_only_prelock_fee_cohort as cohort
from sportsbet.quant.kalshi_market_cohort import digest

COUNTS = (4, 36, 5, 15, 6, 4)


def frozen():
    starts = [datetime(2026, 10, 4, 13, 30, tzinfo=timezone.utc)
              + timedelta(hours=3 * index) for index in range(6)]
    candidates = []
    forecasts = []
    for index, (start, count) in enumerate(zip(starts, COUNTS, strict=True)):
        for number in range(count):
            ticker = f'FIXED-{index}-{number}'
            forecasts.append({'ticker': ticker,
                              'scheduled_game_start_time': start.isoformat()})
            candidates.append({'ticker': ticker})
    decisions = {'candidates': candidates, 'candidates_count': 70,
                 'candidates_sha256': digest(candidates)}
    return {'forecasts': forecasts}, decisions


def test_all_six_missing_groups_preserve_the_full_denominator():
    forecast, decisions = frozen()
    expected = cohort.groups(forecast, decisions)
    report = cohort.evaluate({}, forecast, decisions,
                             {kickoff: (None, None) for kickoff in expected})
    assert list(expected.values()) == list(COUNTS)
    assert report['candidate_states'] == {'both_receipts_missing': 70}
    assert report['groups_with_both_receipts'] == 0
    assert report['complete_cost_scenario'] is False
    assert report['full_cohort_direct_total_cost'] is None
    assert report['conditional_binary_direct_break_even_wins'] is None
    assert report['edge_established'] is False


def test_partial_and_complete_receipts_preserve_the_same_candidates(monkeypatch):
    forecast, decisions = frozen()
    expected = cohort.groups(forecast, decisions)
    fee_receipts = {kickoff: {'evidence_sha256': f'fee-{index}'}
                    for index, kickoff in enumerate(expected)}
    quote_receipts = {kickoff: {'evidence_sha256': f'quote-{index}'}
                      for index, kickoff in enumerate(expected)}
    fee_kickoffs = {id(receipt): kickoff for kickoff, receipt in fee_receipts.items()}
    quote_kickoffs = {id(receipt): kickoff for kickoff, receipt in quote_receipts.items()}

    def verify_fee(_, __, ___, receipt):
        kickoff = fee_kickoffs[id(receipt)]
        return {'kickoff': kickoff, 'frozen_candidates': expected[kickoff]}

    def verify_quote(_, __, ___, receipt):
        kickoff = quote_kickoffs[id(receipt)]
        return {'kickoff': kickoff, 'frozen_candidates': expected[kickoff]}

    def score(_, __, ___, fee, quote):
        kickoff = fee_kickoffs[id(fee)]
        assert quote_kickoffs[id(quote)] == kickoff
        count = expected[kickoff]
        return {'kickoff': kickoff, 'frozen_candidates': count,
                'candidate_states': {'one_contract_cost_modeled': count},
                'modeled_one_contract_costs': count,
                'modeled_subset_direct_total_cost': str(count * .5),
                'modeled_subset_nondirect_total_cost': str(count * .6),
                'fee_receipt_sha256': fee['evidence_sha256'],
                'quote_receipt_sha256': quote['evidence_sha256']}

    monkeypatch.setattr(cohort.fees, 'evaluate', verify_fee)
    monkeypatch.setattr(cohort.prelock, 'evaluate', verify_quote)
    monkeypatch.setattr(cohort.fee_score, 'evaluate', score)
    receipts = {kickoff: (None, None) for kickoff in expected}
    first, second = list(expected)[:2]
    receipts[first] = (fee_receipts[first], quote_receipts[first])
    receipts[second] = (fee_receipts[second], None)
    partial = cohort.evaluate({}, forecast, decisions, receipts)
    assert partial['candidate_states'] == {
        'both_receipts_missing': 30, 'one_contract_cost_modeled': 4,
        'quote_receipt_missing': 36}
    assert partial['modeled_subset_direct_total_cost'] == '2.0'
    assert partial['full_cohort_direct_total_cost'] is None
    receipts[second] = (fee_receipts[first], None)
    with pytest.raises(ValueError, match='another frozen kickoff'):
        cohort.evaluate({}, forecast, decisions, receipts)
    for kickoff in expected:
        receipts[kickoff] = (fee_receipts[kickoff], quote_receipts[kickoff])
    full = cohort.evaluate({}, forecast, decisions, receipts)
    assert full['candidate_states'] == {'one_contract_cost_modeled': 70}
    assert full['groups_with_both_receipts'] == 6
    assert full['full_cohort_direct_total_cost'] == '35.0'
    assert full['conditional_binary_direct_break_even_wins'] == 36
    assert full['roi'] is None and full['edge_established'] is False


def test_group_scope_rejects_missing_extra_or_mutated_candidates():
    forecast, decisions = frozen()
    expected = cohort.groups(forecast, decisions)
    with pytest.raises(ValueError, match='group scope'):
        cohort.evaluate({}, forecast, decisions, {})
    with pytest.raises(ValueError, match='group scope'):
        cohort.evaluate({}, forecast, decisions,
                        {**{key: (None, None) for key in expected}, 'other': (None, None)})
    decisions['candidates'][0]['ticker'] = 'UNKNOWN'
    with pytest.raises(ValueError, match='missing frozen kickoff'):
        cohort.groups(forecast, decisions)
