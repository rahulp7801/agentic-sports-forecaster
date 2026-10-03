"""Tests for the separate outcome-blind 75% paper-candidate diagnostic."""
from datetime import datetime, timezone

import pytest

from sportsbet.quant import kalshi_stat_only_high_probability_eval as audit


def fixtures(monkeypatch, states):
    pre = {'original_market_contracts': 3, 'paper_candidates': 3,
           'first_eligible_settlement_at': '2026-10-06T06:15:00+00:00'}
    monkeypatch.setattr(audit.frozen, 'preflight', lambda *a: (pre, {}))
    monkeypatch.setattr(audit, 'unpack', lambda pair: ({'selections': []}, {}))
    monkeypatch.setattr(audit, 'venue_results', lambda *a, **k: (
        [{'ticker': 'A'}, {'ticker': 'B'}, {'ticker': 'C'}], states))
    decisions = {'candidates': [
        {'ticker': 'A', 'milestone_id': 'G1', 'side': 'yes',
         'model_win_probability': '.75', 'displayed_ask': '.4'},
        {'ticker': 'B', 'milestone_id': 'G2', 'side': 'no',
         'model_win_probability': '.8', 'displayed_ask': '.5'},
        {'ticker': 'C', 'milestone_id': 'G2', 'side': 'yes',
         'model_win_probability': '.7499', 'displayed_ask': '.6'}]}
    return decisions


def run(decisions, settlements=None, now=None):
    return audit.evaluate({}, {}, {}, {}, decisions, None, None,
                          settlements, now=now)


def test_pre_result_keeps_original_denominator_and_reads_no_outcomes(monkeypatch):
    decisions = fixtures(monkeypatch, {})
    def forbidden(*a, **k):
        raise AssertionError('read venue outcome before eligible time')
    monkeypatch.setattr(audit, 'venue_results', forbidden)
    report = run(decisions)
    assert (report['primary_paper_candidates'], report['paper_candidates'],
            report['paper_games']) == (3, 2, 2)
    assert report['mean_frozen_model_win_probability'] == '0.775'
    assert report['mean_displayed_ask'] == '0.45'
    assert report['result_counts'] is None
    assert report['full_group_win_rate'] is None


def test_premature_settlement_refused_before_venue_read(monkeypatch):
    decisions = fixtures(monkeypatch, {})
    monkeypatch.setattr(audit, 'venue_results', lambda *a, **k: 1/0)
    with pytest.raises(ValueError, match='premature'):
        run(decisions, {'evidence_sha256': 'synthetic'},
            datetime.fromisoformat('2026-10-06T06:14:59+00:00'))


def test_missing_outcome_never_becomes_full_group_win_rate(monkeypatch):
    decisions = fixtures(monkeypatch, {'A': ('venue_verified', 'yes'),
        'B': ('not_returned', None), 'C': ('venue_verified', 'no')})
    report = run(decisions, {'evidence_sha256': 'synthetic'},
        datetime.fromisoformat('2026-10-06T06:15:01+00:00'))
    assert report['result_counts'] == {'not_returned': 1, 'venue_verified': 1}
    assert report['verified_subset_win_rate'] == '1'
    assert report['full_group_win_rate'] is None
    assert report['full_group_gross_unit_profit'] is None
    assert report['edge_established'] is False and report['qualified_picks'] == 0


def test_authenticated_full_group_is_scored_without_changing_primary(monkeypatch):
    decisions = fixtures(monkeypatch, {'A': ('venue_verified', 'yes'),
        'B': ('venue_verified', 'yes'), 'C': ('venue_verified', 'no')})
    report = run(decisions, {'evidence_sha256': 'synthetic'},
        datetime.fromisoformat('2026-10-06T06:15:01+00:00'))
    assert report['verified_wins'] == 1
    assert report['full_group_win_rate'] == '0.5'
    assert report['full_group_gross_unit_profit'] == '0.1'
    assert report['primary_paper_candidates'] == 3
    assert report['roi'] is None and report['clv'] is None
