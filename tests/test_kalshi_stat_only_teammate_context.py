from datetime import datetime, timezone
from decimal import Decimal

import pytest

from sportsbet.quant import kalshi_stat_only_teammate_context as context
from sportsbet.quant.kalshi_market_cohort import digest


def test_predeclared_teammate_bands_keep_zero_target_absence_separate():
    assert context.stratum(None, False, False) == 'coverage_unavailable'
    assert context.stratum(Decimal(0), True, False) == 'acute_teammate_zero_prior_targets'
    assert context.stratum(Decimal(0), False, True) == 'questionable_teammate_only'
    assert context.stratum(Decimal(0), False, False) == 'no_reported_skill_teammate_risk'
    assert context.stratum(Decimal('.10'), True, False) == 'acute_teammate_up_to_10pct_prior_targets'
    assert context.stratum(Decimal('.25'), True, False) == 'acute_teammate_10_to_25pct_prior_targets'
    assert context.stratum(Decimal('.250001'), True, False) == 'acute_teammate_over_25pct_prior_targets'
    with pytest.raises(ValueError, match='target share'):
        context.stratum(Decimal('1.1'), True, False)


def test_freeze_requires_original_decision_before_first_kickoff():
    report = {'first_kickoff_at': '2026-10-04T13:30:00+00:00'}
    decisions = {'decided_at': '2026-10-04T03:00:00+00:00'}
    receipt = context.freeze(report, decisions, now=datetime(2026, 10, 4, 5, tzinfo=timezone.utc))
    assert receipt['record_sha256'] == digest({k: v for k, v in receipt.items() if k != 'record_sha256'})
    with pytest.raises(ValueError, match='before first kickoff'):
        context.freeze(report, decisions, now=datetime(2026, 10, 4, 14, tzinfo=timezone.utc))


def test_scoring_keeps_missing_result_and_checks_receipt(monkeypatch):
    report = {
        'first_kickoff_at': '2026-10-04T13:30:00+00:00',
        'rows': [
            dict(ticker='A', milestone_id='g1', side='no', model_win_probability='0.8',
                 displayed_ask='0.7', high_probability=True,
                 teammate_context_stratum='acute_teammate_over_25pct_prior_targets'),
            dict(ticker='B', milestone_id='g2', side='no', model_win_probability='0.9',
                 displayed_ask='0.8', high_probability=True,
                 teammate_context_stratum='no_reported_skill_teammate_risk'),
        ],
    }
    decisions = {'decided_at': '2026-10-04T03:00:00+00:00'}
    receipt = context.freeze(report, decisions, now=datetime(2026, 10, 4, 5, tzinfo=timezone.utc))
    monkeypatch.setattr(context, 'EXPECTED_RECORD_SHA256', receipt['record_sha256'])
    monkeypatch.setattr(context.high, 'evaluate', lambda *args, **kwargs: dict(
        paper_candidates=2, verified_candidates=1, result_counts={'venue_verified':1,'missing':1}))
    monkeypatch.setattr(context.high, 'unpack', lambda pair: ({}, {}))
    monkeypatch.setattr(context.high, 'venue_results', lambda *args, **kwargs: (
        [], {'A':('venue_verified','no'), 'B':('missing',None)}))
    result = context.score(report, receipt, {}, {}, {}, {}, decisions, None, None,
                           {'evidence_sha256':'settlement'}, now=datetime(2026,10,6,7,tzinfo=timezone.utc))
    assert result['verified_candidates'] == 1
    assert result['strata']['acute_teammate_over_25pct_prior_targets']['full_group_brier'] == '0.04'
    assert result['strata']['no_reported_skill_teammate_risk']['full_group_win_rate'] is None
    changed = dict(receipt, rows=[dict(receipt['rows'][0], side='yes'), receipt['rows'][1]])
    with pytest.raises(ValueError, match='receipt changed'):
        context.score(report, changed, {}, {}, {}, {}, decisions, None, None,
                      {'evidence_sha256':'settlement'}, now=datetime(2026,10,6,7,tzinfo=timezone.utc))
