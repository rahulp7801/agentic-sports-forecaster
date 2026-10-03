"""The strict-control cost rollup cannot hide uncaptured fixed candidates."""
from __future__ import annotations

import pytest

from sportsbet.quant import kalshi_stat_only_prelock_net_prior20_cohort as cohort
from tests.test_kalshi_stat_only_prelock_fee_cohort import frozen


def test_no_receipts_retains_all_70_without_full_cohort_claim():
    forecast, decisions = frozen()
    expected = cohort.fee_cohort.groups(forecast, decisions)
    report = cohort.evaluate({}, forecast, decisions, {},
                             {kickoff: (None, None) for kickoff in expected})
    assert report['frozen_candidates'] == 70
    assert report['modeled_cost_subset'] == 0
    assert report['missing_modeled_costs'] == 70
    assert report['candidate_states'] == {'both_receipts_missing': 70}
    assert report['modeled_subset_direct_model_mean_net_margin'] is None
    assert report['full_cohort_direct_model_net_margin_at_least_5pp'] is None
    assert report['qualified_picks'] == 0


def test_partial_and_complete_summaries_keep_same_scope(monkeypatch):
    forecast, decisions = frozen()
    expected = cohort.fee_cohort.groups(forecast, decisions)
    receipts = {kickoff: (None, None) for kickoff in expected}
    first = next(iter(expected))
    receipts[first] = ({'fee': first}, {'quote': first})

    def fee_audit(_, __, ___, present):
        scored = sum(expected[kickoff] for kickoff, pair in present.items()
                     if pair[0] is not None and pair[1] is not None)
        return {'modeled_one_contract_costs': scored,
                'groups_with_both_receipts': sum(
                    both[0] is not None and both[1] is not None
                    for both in present.values()),
                'candidate_states': {'one_contract_cost_modeled': scored,
                                     'both_receipts_missing': 70 - scored},
                'group_reports_sha256': 'fee-audit'}

    def net_group(_, __, ___, ____, fee, quote):
        kickoff = fee['fee']
        assert quote['quote'] == kickoff
        count = expected[kickoff]
        report = {'kickoff': kickoff, 'frozen_candidates': count,
                  'modeled_cost_subset': count}
        report.update({key: count for key in cohort.MARGIN_KEYS})
        report.update({key: '.10' for key in cohort.MEAN_KEYS})
        return report

    monkeypatch.setattr(cohort.fee_cohort, 'evaluate', fee_audit)
    monkeypatch.setattr(cohort.net_prior20, 'evaluate', net_group)
    partial = cohort.evaluate({}, forecast, decisions, {}, receipts)
    assert partial['modeled_cost_subset'] == 4
    assert partial['missing_modeled_costs'] == 66
    assert partial['modeled_subset_direct_model_net_margin_at_least_5pp'] == 4
    assert partial['full_cohort_direct_model_net_margin_at_least_5pp'] is None
    for kickoff in expected:
        receipts[kickoff] = ({'fee': kickoff}, {'quote': kickoff})
    full = cohort.evaluate({}, forecast, decisions, {}, receipts)
    assert full['modeled_cost_subset'] == 70
    assert full['complete_cost_scenario'] is True
    assert full['full_cohort_direct_model_net_margin_at_least_5pp'] == 70
    assert full['full_cohort_direct_model_mean_net_margin'] == '0.10'
    assert full['edge_established'] is False


def test_disagreement_with_fee_audit_fails_closed(monkeypatch):
    forecast, decisions = frozen()
    expected = cohort.fee_cohort.groups(forecast, decisions)
    monkeypatch.setattr(cohort.fee_cohort, 'evaluate', lambda *args: {
        'modeled_one_contract_costs': 1, 'groups_with_both_receipts': 0,
        'candidate_states': {}, 'group_reports_sha256': 'bad'})
    with pytest.raises(ValueError, match='denominators'):
        cohort.evaluate({}, forecast, decisions, {},
                        {kickoff: (None, None) for kickoff in expected})
