"""Closed prospective accuracy cohort for original NFL receiving paper selections.

The original paper selector fixes player, game, side, line and matching price.
Verified current-role context may only retain or abstain from that selection.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import mean

from sportsbet.ledger import utc_timestamp
from sportsbet.quant import individual_pick_context_audit as context

CONTEXT_IMPLEMENTATION_SHA256 = '9262a5bafcc92c611dec5b9ce3f5bfce383ae749fc5f2cba15b5dc5cdae5fd71'
ROLE_IMPLEMENTATION_SHA256 = 'cd704fc37ad0ff3e85a0e21b56a6762fb57c6039763903adcac95a93e94b3ddc'
ROLE_ARTIFACT_SHA256 = '7d217ac9a96c62a2f9d41a8f0037ed2cc2d122570d9a8be993530d95fd787582'

PROTOCOL = {
    'version': 'nfl-receiving-individual-pick-audit-v1',
    'frozen_at': '2026-10-01T13:00:00+00:00',
    'original_policy': 'model-selection-raw-v1',
    'candidate_version': 'nfl-recent-role-shadow-v2',
    'markets': ['receptions', 'rec_yds'],
    'original_probability_floor': .75,
    'recent_probability_floor': .75,
    'current_role_probability_floor': .75,
    'minimum_current_team_season_games': 2,
    'maximum_latest_game_gap_days': 30,
    'cohort_size': 50,
    'minimum_distinct_games': 25,
    'automatic_promotion': False,
}


def _check_implementation():
    source = Path(context.__file__).read_text(encoding='utf-8').encode()
    if hashlib.sha256(source).hexdigest() != CONTEXT_IMPLEMENTATION_SHA256:
        raise ValueError('Frozen current-context audit helper changed; new protocol required')
    if (context.role.implementation_sha256() != ROLE_IMPLEMENTATION_SHA256
            or context.role.ARTIFACT_SHA256 != ROLE_ARTIFACT_SHA256):
        raise ValueError('Frozen receiving-role candidate changed; new protocol required')


def _paired_brier(entries):
    against_market = defaultdict(list)
    against_original = defaultdict(list)
    for item in entries:
        if type(item['outcome']) is not bool:
            continue
        y = int(item['outcome'])
        candidate = item['context']['role_probability']
        against_market[item['game_id']].append((candidate-y)**2-(item['market_probability']-y)**2)
        against_original[item['game_id']].append((candidate-y)**2-(item['probability']-y)**2)
    market = [v for group in against_market.values() for v in group]
    original = [v for group in against_original.values() for v in group]
    return dict(candidate_minus_market=mean(market) if market else None,
        candidate_minus_market_game_cluster_95=context.search.frozen.cluster_interval(against_market),
        candidate_minus_original=mean(original) if original else None,
        candidate_minus_original_game_cluster_95=context.search.frozen.cluster_interval(against_original))


def audit(receipts, predictions, now):
    context.require_matching_runtime()
    _check_implementation()
    base = context.audit(receipts, predictions, now)
    result = dict(protocol=PROTOCOL, observed_at=now.isoformat(),
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source_audit=base['source_audit'], status='collecting_fixed_cohort',
        promote=False, target_verified=False, evidence_criteria_met=False,
        limitations=[
            'Private paper selections, not accepted dashboard picks or bets.',
            'The first 50 eligible original selections are fixed by receipt time before outcomes.',
            'An incomplete or favorable early result cannot establish a 75% win rate or edge.',
            'Review is required even if every frozen evidence criterion passes.'])
    if base['status'] == 'invalid_source_evidence':
        result['status'] = 'invalid_source_evidence'
        return result
    cutoff = utc_timestamp(PROTOCOL['frozen_at'])
    times = {r['prediction_id']: utc_timestamp(str(r['recorded_at'])) for r in receipts
        if r['sport'] == 'nfl' and r['protocol'] == PROTOCOL['original_policy']}
    by_id = {row['prediction_id']: row for row in predictions}
    scoped = [entry for entry in base['selections']
        if entry['prediction_id'] in times and times[entry['prediction_id']] >= cutoff
        and utc_timestamp(by_id[entry['prediction_id']]['captured_at']) >= cutoff
        and entry['prop_type'] in PROTOCOL['markets']]
    eligible = sorted((entry for entry in scoped
        if entry['rules']['recent_and_current_role_75']),
        key=lambda entry: (times[entry['prediction_id']], str(entry['prediction_id'])))
    cohort = eligible[:PROTOCOL['cohort_size']]
    summary = context.summarize(cohort, now)
    brier = _paired_brier(cohort)
    closed = len(cohort) == PROTOCOL['cohort_size']
    settled = closed and summary['pending'] == 0
    enough_games = summary['settled_games'] >= PROTOCOL['minimum_distinct_games']
    win_interval = summary['win_rate_game_cluster_95']
    roi_interval = summary['roi_game_cluster_95']
    market_interval = brier['candidate_minus_market_game_cluster_95']
    original_interval = brier['candidate_minus_original_game_cluster_95']
    meets = bool(settled and enough_games and summary['win_rate'] is not None
        and summary['win_rate'] >= .75 and win_interval and win_interval[0] >= .75
        and roi_interval and roi_interval[0] > 0
        and market_interval and market_interval[1] < 0
        and original_interval and original_interval[1] < 0)
    result.update(coverage=dict(original_receiving_selections=len(scoped),
            original_75=sum(entry['rules']['original_75'] for entry in scoped),
            original_75_with_verified_context=sum(entry['rules']['original_75']
                and entry['context']['available'] for entry in scoped),
            eligible_agreements=len(eligible),
            excluded_later_eligible=max(0, len(eligible)-len(cohort)),
            unavailable_context_reasons=base['coverage']['unavailable_reasons']),
        cohort_closed=closed, cohort_prediction_ids=[item['prediction_id'] for item in cohort],
        rule=summary | brier, evidence_criteria_met=meets,
        status='collecting_fixed_cohort' if not closed else
            'awaiting_cohort_settlement' if not settled else
            'insufficient_fixed_cohort' if not enough_games else
            'review_required' if meets else 'evidence_not_demonstrated')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evidence = json.loads(args.inputs.read_text(encoding='utf-8'))
    report = audit(evidence['receipts'], evidence['predictions'], datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print('Private fixed-cohort receiving accuracy audit completed')


if __name__ == '__main__':
    main()
