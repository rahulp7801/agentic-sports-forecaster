"""Post-result paper accounting stays conditional on all frozen evidence."""
from __future__ import annotations

from decimal import Decimal

import pytest

from sportsbet.quant import kalshi_stat_only_prelock_paper_result as result
from sportsbet.quant import kalshi_stat_only_prelock_fee_cohort as fees
from sportsbet.quant.kalshi_market_cohort import digest

HASH = 'a' * 64


def fixture():
    rows = [{'ticker': f'FIXED-{index}', 'side': 'no',
             'milestone_id': f'GAME-{index // 10}'} for index in range(70)]
    decisions = {'candidates': rows, 'candidates_count': 70,
                 'candidates_sha256': digest(rows)}
    costs = {'protocol': fees.VERSION, 'frozen_candidates': 70,
             'frozen_kickoff_groups': 6,
             'candidate_states': {'one_contract_cost_modeled': 70},
             'modeled_one_contract_costs': 70,
             'complete_cost_scenario': True,
             'full_cohort_direct_total_cost': '42.1',
             'full_cohort_nondirect_total_cost': '42.7',
             'group_reports_sha256': HASH}
    states = {row['ticker']: ('venue_verified', 'no' if index < 52 else 'yes')
              for index, row in enumerate(rows)}
    return decisions, costs, states


def test_complete_venue_and_fee_evidence_yields_only_conditional_paper_profit():
    decisions, costs, states = fixture()
    report = result.score_results(decisions, costs, states,
                                  settlement_sha256=HASH)
    assert report['frozen_candidates'] == report['verified_result_candidates'] == 70
    assert report['verified_result_games'] == 7
    assert report['full_cohort_wins'] == 52
    assert report['full_cohort_win_rate'] == str(Decimal(52)/70)
    assert report['full_cohort_hypothetical_direct_unit_profit'] == '9.9'
    assert report['full_cohort_hypothetical_nondirect_unit_profit'] == '9.3'
    assert report['actual_fills_verified'] is False
    assert report['roi'] is None and report['repeatable_edge_established'] is False
    assert report['qualified_picks'] == 0


def test_missing_result_or_cost_blocks_full_profit_without_dropping_candidates():
    decisions, costs, states = fixture()
    states['FIXED-0'] = ('not_returned', None)
    report = result.score_results(decisions, costs, states,
                                  settlement_sha256=HASH)
    assert report['result_states'] == {'not_returned': 1, 'venue_verified': 69}
    assert report['verified_subset_wins'] == 51
    assert report['full_cohort_win_rate'] is None
    assert report['full_cohort_hypothetical_direct_unit_profit'] is None
    states['FIXED-0'] = ('venue_verified', 'no')
    costs['candidate_states'] = {'one_contract_cost_modeled': 69,
                                 'fee_unavailable': 1}
    costs['modeled_one_contract_costs'] = 69
    costs['complete_cost_scenario'] = False
    costs['full_cohort_direct_total_cost'] = None
    costs['full_cohort_nondirect_total_cost'] = None
    report = result.score_results(decisions, costs, states,
                                  settlement_sha256=HASH)
    assert report['full_cohort_wins'] == 52
    assert report['costed_candidates'] == 69
    assert report['full_cohort_hypothetical_direct_unit_profit'] is None


def test_scope_and_result_mutations_fail_closed():
    decisions, costs, states = fixture()
    decisions['candidates_count'] = 69
    with pytest.raises(ValueError, match='commitment'):
        result.score_results(decisions, costs, states, settlement_sha256=HASH)
    decisions['candidates_count'] = 70
    states['FIXED-0'] = ('not_returned', 'no')
    with pytest.raises(ValueError, match='Unverified'):
        result.score_results(decisions, costs, states, settlement_sha256=HASH)
    states.pop('FIXED-0')
    with pytest.raises(ValueError, match='missed frozen'):
        result.score_results(decisions, costs, states, settlement_sha256=HASH)
    decisions, costs, states = fixture()
    costs['candidate_states'] = {'one_contract_cost_modeled': 69}
    with pytest.raises(ValueError, match='denominator'):
        result.score_results(decisions, costs, states, settlement_sha256=HASH)


def test_capture_wrapper_requires_full_postgame_gate_and_record_commitment():
    from copy import deepcopy
    from sportsbet.quant.clock_attestation import HOSTS, VERSION as CLOCK_VERSION
    from sportsbet.quant.kalshi_stat_only_settlement_capture import VERSION as CAPTURE_VERSION

    pre = {'original_market_contracts': 452,
           'first_eligible_settlement_at': '2026-10-06T06:15:00+00:00'}
    receipt = {'protocol': CAPTURE_VERSION,
               'original_market_contracts': 452,
               'first_eligible_settlement_at': pre['first_eligible_settlement_at'],
               'clock_proof': {'protocol': CLOCK_VERSION,
                   'local_clock_acceptable': True,
                   'checked_at': '2026-10-06T06:20:00+00:00',
                   'observations': [dict(host=host,
                       request_started_at=start, response_received_at=end,
                       server_date=end, rtt_seconds=1,
                       server_minus_local_seconds=.5, age=None, http_status=200)
                       for host, start, end in zip(HOSTS,
                           ('2026-10-06T06:19:58+00:00',
                            '2026-10-06T06:19:59+00:00'),
                           ('2026-10-06T06:19:59+00:00',
                            '2026-10-06T06:20:00+00:00'), strict=True)]},
               'evidence': {'pages': [{'request_started_at':
                   '2026-10-06T06:20:15+00:00',
                   'received_at': '2026-10-06T06:20:30+00:00'}]},
               'captured_at': '2026-10-06T06:20:31+00:00'}
    receipt['record_sha256'] = digest(receipt)
    result.verify_capture_wrapper(receipt, pre)
    changed = deepcopy(receipt)
    changed['evidence']['pages'][0]['request_started_at'] = '2026-10-06T06:14:59+00:00'
    changed['record_sha256'] = digest({key: value for key, value in changed.items()
                                       if key != 'record_sha256'})
    with pytest.raises(ValueError, match='gate'):
        result.verify_capture_wrapper(changed, pre)
    changed = deepcopy(receipt)
    changed['captured_at'] = '2026-10-06T06:20:32+00:00'
    with pytest.raises(ValueError, match='commitment'):
        result.verify_capture_wrapper(changed, pre)
    for field, value in [('age', '30'), ('age', False), ('age', '00'),
                         ('age', 0.0), ('http_status', 503),
                         ('server_minus_local_seconds', 1.5),
                         ('server_date', '2026-10-06T06:20:04+00:00')]:
        changed = deepcopy(receipt)
        changed['clock_proof']['observations'][0][field] = value
        changed['record_sha256'] = digest({key: value for key, value in changed.items()
                                           if key != 'record_sha256'})
        with pytest.raises(ValueError, match='clock'):
            result.verify_capture_wrapper(changed, pre)
