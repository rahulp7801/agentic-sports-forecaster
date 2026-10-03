"""Fixed, outcome-blind denominator and game-cluster uncertainty checks."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

import pytest

from sportsbet.quant import kalshi_stat_only_win_uncertainty as audit
from sportsbet.quant.kalshi_market_cohort import digest


def fixture():
    rows = [dict(ticker=f'FIXED-{index}', side='no',
                 milestone_id=f'GAME-{index % 8 if index < 11 else 8 + (index-11) % 7}',
                 model_win_probability='0.80' if index < 11 else '0.65')
            for index in range(70)]
    decisions = {'candidates': rows, 'candidates_count': 70,
                 'candidate_games': 15, 'candidates_sha256': digest(rows)}
    states = {row['ticker']: ('venue_verified', 'yes' if index % 4 == 0 else 'no')
              for index, row in enumerate(rows)}
    return decisions, states


def test_complete_fixed_groups_report_cluster_uncertainty_without_edge_promotion():
    decisions, states = fixture()
    first = audit.evaluate(decisions, states, settlement_sha256='a'*64)
    assert first == audit.evaluate(decisions, states, settlement_sha256='a'*64)
    all_rows, high = first['groups']['all_70'], first['groups']['model_p_at_least_75']
    assert (all_rows['frozen_candidates'], all_rows['frozen_games']) == (70, 15)
    assert (high['frozen_candidates'], high['frozen_games']) == (11, 8)
    assert all_rows['verified_subset_wins'] == 52
    assert high['verified_subset_wins'] == 8
    assert all_rows['full_win_rate'] == str(Decimal(52)/70)
    assert high['full_win_rate'] == str(Decimal(8)/11)
    for group in (all_rows, high):
        assert group['complete'] is True
        assert group['fully_verified_games'] == group['frozen_games']
        for interval in group['full_game_cluster_95'].values():
            assert len(interval) == 2
            assert 0 <= float(interval[0]) <= float(interval[1]) <= 1
    assert first['actual_fills_verified'] is False
    assert first['roi'] is None and first['repeatable_edge_established'] is False
    assert first['qualified_picks'] == 0


def test_missing_result_keeps_both_full_rates_and_intervals_null():
    decisions, states = fixture()
    states['FIXED-0'] = ('not_returned', None)
    report = audit.evaluate(decisions, states, settlement_sha256='a'*64)
    all_rows, high = report['groups']['all_70'], report['groups']['model_p_at_least_75']
    assert all_rows['verified_subset_candidates'] == 69
    assert all_rows['fully_verified_games'] == 14
    assert high['verified_subset_candidates'] == 10
    assert high['fully_verified_games'] == 7
    for group in (all_rows, high):
        assert group['complete'] is False
        assert group['full_win_rate'] is None
        assert group['full_equal_game_win_rate'] is None
        assert group['full_game_cluster_95'] is None


def test_reselection_or_mutated_frozen_scope_fails_closed():
    decisions, states = fixture()
    changed = deepcopy(decisions)
    changed['candidates'][11]['model_win_probability'] = '0.80'
    changed['candidates_sha256'] = digest(changed['candidates'])
    with pytest.raises(ValueError, match='diagnostic changed'):
        audit.evaluate(changed, states, settlement_sha256='a'*64)
    states['FIXED-1'] = ('not_returned', 'no')
    with pytest.raises(ValueError, match='Unverified'):
        audit.evaluate(decisions, states, settlement_sha256='a'*64)
    del states['FIXED-1']
    with pytest.raises(ValueError, match='missed'):
        audit.evaluate(decisions, states, settlement_sha256='a'*64)
