"""Read-only prospective scoring for the untraded NFL stat-only transfer."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone

import numpy as np

from sportsbet.ledger import utc_timestamp
from sportsbet.quant import nfl_stat_only_shadow as shadow
from sportsbet.quant.history_tuning import Example, compare, score
from sportsbet.quant.market_baseline import verified_recorded_market_baseline
from sportsbet.quant.priced_market_audit import _eligible, _verified_outcome
from sportsbet.quant.nfl_recent_role_params import BASELINE_VERSION


def _recorded_shadow_is_intact(row: dict) -> bool:
    """Distinguish a replayable abstention from a damaged paper receipt."""
    try:
        recorded = utc_timestamp(row['stat_only_shadow_recorded_at'])
        decision = utc_timestamp(row['captured_at'])
        deadline = min(utc_timestamp(row['game_start_time']),
                       utc_timestamp(row['quote_time']) + timedelta(seconds=300))
        return (decision <= recorded < deadline
                and row['stat_only_shadow'] == shadow.shadow_record(row))
    except (KeyError, TypeError, ValueError, ArithmeticError, OverflowError):
        return False


def report_stat_only(rows: list[dict]) -> dict:
    artifact = shadow.artifact()
    report = dict(model_version=shadow.VERSION, policy_version=shadow.POLICY,
                  artifact_sha256=shadow.ARTIFACT_SHA256,
                  implementation_sha256=shadow.implementation_sha256(),
                  frozen_at=shadow.FROZEN_AT, generated_at=datetime.now(timezone.utc).isoformat(),
                  sport='nfl', status='collecting', promote=False, edge_established=False,
                  scope='Untraded prospective stat-only correction; no ROI or consumer promotion.',
                  minimum_paired_games=artifact['minimum_paired_games'],
                  markets={}, excluded=0)
    attempts = []
    for row in rows:
        receipt = row.get('stat_only_shadow')
        if row.get('sport') != 'nfl' or not isinstance(receipt, dict):
            continue
        if (_eligible(row, 'nfl', BASELINE_VERSION) is None
                or utc_timestamp(row['captured_at']) < utc_timestamp(shadow.FROZEN_AT)):
            report['excluded'] += 1
            continue
        attempts.append(row)
    attempts.sort(key=lambda row: (utc_timestamp(row['captured_at']),
                                   row['direction'] != 'over', str(row['prediction_id'])))
    selected = {}
    for row in attempts:
        key = (row['game_id'], row['player_id'], row['prop_type'], float(row['line']))
        selected.setdefault(key, row)  # Before shadow status, price pairing, or outcome.
    report.update(recorded_attempts=len(attempts), earliest_attempts=len(selected),
                  duplicate_attempts=len(attempts)-len(selected))
    for prop in sorted(shadow.MARKETS):
        cohort = [row for row in selected.values() if row['prop_type'] == prop]
        counts = Counter(attempts=len(cohort))
        reasons = Counter()
        examples = []
        candidate_p = []
        market_p = []
        for row in cohort:
            if not _recorded_shadow_is_intact(row):
                counts['unavailable'] += 1
                counts['invalid_shadow_receipts'] += 1
                reasons['invalid_shadow_record'] += 1
                continue
            if row['stat_only_shadow']['status'] == 'unavailable':
                counts['unavailable'] += 1
                reasons[row['stat_only_shadow']['reason']] += 1
                continue
            probability = shadow.verified_recorded_shadow_probability(row)
            if probability is None:
                counts['unavailable'] += 1
                counts['invalid_shadow_receipts'] += 1
                reasons['invalid_shadow_record'] += 1
                continue
            counts['valid_predictions'] += 1
            market = verified_recorded_market_baseline(row)
            counts['paired_predictions' if market is not None else 'unpaired'] += 1
            outcome = _verified_outcome(row)
            if type(outcome) is not bool:
                counts['pending'] += 1
                continue
            counts['verified_decided'] += 1
            if market is None:
                continue
            counts['paired_decided'] += 1
            examples.append(Example('evaluate', row['game_id'], row['player_id'],
                                    date.fromisoformat(row['game_date']), float(row['line']),
                                    int(outcome), float(row['model_probability']),
                                    market, probability, (), row['model_sample_size'], False))
            candidate_p.append(probability)
            market_p.append(market)
        result = dict(status='insufficient_data',
                      counts={key: counts[key] for key in (
                          'attempts', 'unavailable', 'valid_predictions', 'unpaired',
                          'paired_predictions', 'pending', 'verified_decided', 'paired_decided',
                          'invalid_shadow_receipts')},
                      unavailable_reasons=dict(reasons), promote=False,
                      paired_games=len({e.game for e in examples}),
                      paired_players=len({e.player for e in examples}))
        if examples:
            baseline = np.asarray([e.base for e in examples])
            candidate = np.asarray(candidate_p)
            market = np.asarray(market_p)
            result.update(production=score(examples, baseline),
                          candidate=score(examples, candidate),
                          market=score(examples, market),
                          candidate_minus_production=compare(examples, baseline, candidate),
                          candidate_minus_market=compare(examples, market, candidate))
            if result['paired_games'] >= artifact['minimum_paired_games']:
                supported = all(result[comparison][metric+'_'+cluster+'_95'] is not None
                                and result[comparison][metric+'_'+cluster+'_95'][1] < 0
                                for comparison in ('candidate_minus_production', 'candidate_minus_market')
                                for metric in ('brier', 'log_loss')
                                for cluster in ('game', 'player'))
                result['status'] = 'prospective_probability_support' if supported else 'evidence_not_demonstrated'
        if counts['invalid_shadow_receipts']:
            result['status'] = 'invalid_shadow_receipts'
        report['markets'][prop] = result
    report['invalid_shadow_receipts'] = sum(
        market['counts']['invalid_shadow_receipts'] for market in report['markets'].values())
    if report['invalid_shadow_receipts']:
        report['status'] = 'invalid_shadow_receipts'
        for market in report['markets'].values():
            market['status'] = 'invalid_shadow_receipts'
    return report
