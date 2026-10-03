"""Fixed high-probability costs cannot silently shrink or swap contracts."""
from decimal import Decimal

import pytest

from sportsbet.quant import kalshi_stat_only_high_fee_scenario as scenario


def fixed(monkeypatch):
    kickoffs = [f'2026-10-04T{hour}:00:00+00:00' for hour in (13, 17, 20, 21)]
    selected = [{'ticker': f'H{i}', 'milestone_id': f'G{i % 8}',
                 'side': 'no', 'model_win_probability': '.8'} for i in range(11)]
    candidates = selected + [{'ticker': f'L{i}', 'milestone_id': f'OTHER{i}',
                              'side': 'yes', 'model_win_probability': '.6'}
                             for i in range(59)]
    forecast = {'forecasts': [{'ticker': row['ticker'],
                  'scheduled_game_start_time': kickoffs[i % 4]}
                 for i, row in enumerate(selected)]}
    control = {'forecast_rows': [{'ticker': row['ticker'],
                                 'prior20_over_probability': '.3'} for row in selected]}
    monkeypatch.setattr(scenario, 'HIGH_TICKERS_SHA256',
                        scenario.digest(sorted(row['ticker'] for row in selected)))
    high_report = {'selected_tickers_sha256': scenario.HIGH_TICKERS_SHA256,
                   'paper_candidates': 11, 'paper_games': 8}
    receipts = {kickoff: ({'kickoff': kickoff}, {}) for kickoff in kickoffs}
    costs = {kickoff: [{'ticker': row['ticker'], 'milestone_id': row['milestone_id'],
                       'ask': '.5', 'direct_total': '.5', 'nondirect_total': '.5'}
                      for i, row in enumerate(selected) if kickoffs[i % 4] == kickoff]
             for kickoff in kickoffs}
    def fee_report(_, __, ___, receipt, _____, *, include_cost_rows):
        assert include_cost_rows
        kickoff = receipt['kickoff']
        return {'kickoff': kickoff, 'fee_receipt_sha256': 'fee',
                'quote_receipt_sha256': 'quote',
                'candidate_states': {'one_contract_cost_modeled': len(costs[kickoff])},
                'modeled_cost_rows': costs[kickoff]}
    monkeypatch.setattr(scenario.fees, 'evaluate', fee_report)
    return forecast, {'candidates': candidates}, control, high_report, receipts, costs


def test_full_fixed_11_has_explicit_break_even_and_no_edge(monkeypatch):
    forecast, decisions, control, high_report, receipts, _ = fixed(monkeypatch)
    result = scenario.evaluate({}, forecast, decisions, control, high_report, receipts)
    assert result['observed_high_probability_costs'] == 11
    assert result['fixed_high_probability_games'] == 8
    assert result['direct_full_cost_total'] == '5.5'
    assert result['direct_full_binary_break_even_wins'] == 6
    assert Decimal(result['direct_model_full_projected_net_units']) == Decimal('3.3')
    assert Decimal(result['direct_strict_prior20_full_projected_net_units']) == Decimal('2.2')
    assert not result['edge_established']


def test_missing_or_cross_group_cost_cannot_become_full_11(monkeypatch):
    forecast, decisions, control, high_report, receipts, costs = fixed(monkeypatch)
    first = next(iter(costs))
    removed = costs[first].pop()
    partial = scenario.evaluate({}, forecast, decisions, control, high_report, receipts)
    assert partial['observed_high_probability_costs'] == 10
    assert partial['direct_full_cost_total'] is None
    assert partial['direct_model_full_projected_net_units'] is None
    other = next(k for k in costs if k != first)
    costs[other].append(removed)
    with pytest.raises(ValueError, match='cross-group'):
        scenario.evaluate({}, forecast, decisions, control, high_report, receipts)
