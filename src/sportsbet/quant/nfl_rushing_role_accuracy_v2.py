"""Closed prospective cohort for individual NFL rushing paper picks.

Version 1 remains available for reproducibility, but did not close its sample.
This version fixes the first 50 eligible receipts without looking at outcomes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from sportsbet.ledger import utc_timestamp
from sportsbet.quant import nfl_rushing_role_accuracy as v1

V1_IMPLEMENTATION_SHA256 = '7989b14c0e2217a38f42eda56377bbbd14c160cddca738df6215882dd8f66023'

PROTOCOL = {
    'version': 'nfl-rushing-individual-pick-audit-v2',
    'frozen_at': '2026-10-01T06:30:00+00:00',
    'candidate_version': 'nfl-rushing-role-shadow-v1',
    'source_policy': 'model-selection-raw-v1',
    'original_probability_floor': .75,
    'rushing_role_probability_floor': .75,
    'cohort': 'First 50 valid original rushing paper selections after frozen_at where both recorded probabilities are at least 75%, ordered by recorded_at then prediction_id. Later selections cannot enter.',
    'cohort_size': 50,
    'minimum_distinct_games': 25,
    'automatic_promotion': False,
}


def audit(receipts, predictions, now):
    v1.require_matching_runtime()
    if hashlib.sha256(Path(v1.__file__).read_text(encoding='utf-8').encode()).hexdigest() != V1_IMPLEMENTATION_SHA256:
        raise ValueError('Frozen v1 audit helper changed; new protocol required')
    base = v1.audit(receipts, predictions, now)
    result = dict(protocol=PROTOCOL, observed_at=now.isoformat(),
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source_audit=base['source_audit'], status='collecting_fixed_cohort',
        promote=False, target_verified=False, evidence_criteria_met=False,
        coverage={}, rule={}, limitations=[
            'This is a fixed prospective paper cohort, not accepted dashboard picks or bets.',
            'The first 50 eligible selections are locked by receipt order before outcomes are examined.',
            'A favorable early result does not establish a 75% win rate or betting edge.',
            'Review is required even if every evidence threshold passes.'])
    if base['status'] == 'invalid_source_evidence':
        result['status'] = 'invalid_source_evidence'
        return result
    cutoff = utc_timestamp(PROTOCOL['frozen_at'])
    times = {r['prediction_id']: utc_timestamp(str(r['recorded_at']))
             for r in receipts if r['sport'] == 'nfl'
             and r['protocol'] == PROTOCOL['source_policy']}
    scoped = [s for s in base['selections']
              if s['prediction_id'] in times and times[s['prediction_id']] >= cutoff]
    eligible = sorted((s for s in scoped if s['agreement_75']),
        key=lambda s: (times[s['prediction_id']], str(s['prediction_id'])))
    cohort = eligible[:PROTOCOL['cohort_size']]
    summary = v1.summarize(cohort, now)
    closed = len(cohort) == PROTOCOL['cohort_size']
    settled = closed and summary['pending'] == 0
    enough_games = summary['distinct_decided_games'] >= PROTOCOL['minimum_distinct_games']
    win_interval = summary['win_rate_game_cluster_95']
    roi_interval = summary['roi_game_cluster_95']
    brier_interval = summary['brier_difference_game_cluster_95']
    meets = bool(settled and enough_games and summary['win_rate'] is not None
        and summary['win_rate'] >= .75 and win_interval and win_interval[0] >= .75
        and roi_interval and roi_interval[0] > 0
        and brier_interval and brier_interval[1] < 0)
    result.update(
        coverage=dict(original_rushing_selections=len(scoped),
            original_75=sum(s['original_75'] for s in scoped),
            original_75_with_candidate=sum(s['original_75'] and s['role_probability'] is not None for s in scoped),
            eligible_agreements=len(eligible), excluded_later_eligible=max(0, len(eligible)-len(cohort)),
            missing_candidate_reasons=base['coverage']['unavailable_reasons']),
        cohort_closed=closed, cohort_pending=summary['pending'],
        cohort_prediction_ids=[s['prediction_id'] for s in cohort],
        rule=summary, evidence_criteria_met=meets,
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
    v1.require_matching_runtime()
    evidence = json.loads(args.inputs.read_text(encoding='utf-8'))
    report = audit(evidence['receipts'], evidence['predictions'], datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print('Private fixed-cohort rushing audit completed')


if __name__ == '__main__':
    main()
