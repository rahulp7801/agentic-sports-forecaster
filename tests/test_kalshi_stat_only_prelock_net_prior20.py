"""Fee-aware strict-control comparisons preserve the fixed denominator."""
from decimal import Decimal

import pytest

from sportsbet.quant.kalshi_market_cohort import digest
from sportsbet.quant.kalshi_stat_only_prelock_net_prior20 import summarize


def test_no_complement_fee_modes_and_missing_candidate():
    selected = [
        {'ticker': 'NO', 'milestone_id': 'G1', 'side': 'no',
         'model_win_probability': '.75'},
        {'ticker': 'YES', 'milestone_id': 'G2', 'side': 'yes',
         'model_win_probability': '.55'},
        {'ticker': 'MISSING', 'milestone_id': 'G2', 'side': 'no',
         'model_win_probability': '.8'}]
    control = {'forecast_rows': [
        {'ticker': 'NO', 'prior20_over_probability': '.30'},
        {'ticker': 'YES', 'prior20_over_probability': '.45'},
        {'ticker': 'MISSING', 'prior20_over_probability': '.1'}]}
    rows = [
        {'ticker': 'NO', 'milestone_id': 'G1', 'ask': '.60',
         'direct_total': '.62', 'nondirect_total': '.64'},
        {'ticker': 'YES', 'milestone_id': 'G2', 'ask': '.48',
         'direct_total': '.51', 'nondirect_total': '.53'}]
    fee = {'modeled_cost_rows': rows, 'modeled_one_contract_costs': 2,
           'modeled_cost_rows_sha256': digest(rows),
           'fee_receipt_sha256': 'fee', 'quote_receipt_sha256': 'quote',
           'candidate_states': {'one_contract_cost_modeled': 2,
                                'fee_unavailable': 1}}
    report = summarize(selected, control, fee)
    assert report['frozen_candidates'] == 3
    assert report['modeled_cost_subset'] == 2
    assert report['missing_modeled_costs'] == 1
    assert report['direct_model_net_margin_at_least_5pp'] == 1
    assert report['direct_strict_prior20_net_margin_at_least_5pp'] == 1
    assert report['nondirect_strict_prior20_net_margin_at_least_5pp'] == 1
    assert Decimal(report['direct_model_mean_net_margin']) == Decimal('.085')
    assert report['actual_fills_verified'] is False
    assert report['edge_established'] is False


def test_cost_row_change_fails_closed():
    selected = [{'ticker': 'A', 'milestone_id': 'G1', 'side': 'yes',
                 'model_win_probability': '.6'}]
    control = {'forecast_rows': [{'ticker': 'A',
                                  'prior20_over_probability': '.5'}]}
    rows = [{'ticker': 'A', 'milestone_id': 'G2', 'ask': '.4',
             'direct_total': '.41', 'nondirect_total': '.42'}]
    fee = {'modeled_cost_rows': rows, 'modeled_one_contract_costs': 1,
           'modeled_cost_rows_sha256': digest(rows)}
    with pytest.raises(ValueError, match='identity'):
        summarize(selected, control, fee)
