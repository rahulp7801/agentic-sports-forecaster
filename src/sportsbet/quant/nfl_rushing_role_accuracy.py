"""Private prospective accuracy audit of the predeclared NFL rushing-role rule.

The original raw-model paper receipt fixes the player, side, line and price.
The candidate may only abstain or agree on that same original selection.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import platform
from statistics import mean
import sys

from sportsbet.ledger import utc_timestamp
from sportsbet.quant import edge_search_stress as search
from sportsbet.quant import model_selection_paper as paper
from sportsbet.quant import nfl_rushing_role_shadow as rush

PROTOCOL = {'version': 'nfl-rushing-individual-pick-audit-v1',
    'frozen_at': rush.FROZEN_AT, 'sport': 'nfl', 'source_policy': 'raw_model',
    'market': rush.MARKET, 'original_probability_floor': .75,
    'rushing_role_probability_floor': .75, 'minimum_decisions': 50,
    'minimum_distinct_games': 25, 'automatic_promotion': False,
    'rule': 'Original raw-model paper selection qualifies only when both recorded model and prospectively committed rushing-role probabilities are at least 75%; no replacement quote or selection.'}


def require_matching_runtime():
    # v2 source inputs contain gzip bytes; Windows and Linux encode different OS bytes.
    if (platform.system() != 'Linux' or platform.python_implementation() != 'CPython'
            or sys.version_info[:2] != (3, 12)
            or gzip.compress(b'runtime-check', compresslevel=6, mtime=0)[9] != 3):
        raise ValueError('Frozen rushing-role replay requires Linux CPython 3.12')


def summarize(entries, now):
    decided = [entry for entry in entries if type(entry['outcome']) is bool]
    games = defaultdict(list); returns = defaultdict(list); brier_differences = defaultdict(list)
    for entry in decided:
        games[entry['game_id']].append(int(entry['outcome']))
        returns[entry['game_id']].append(search.profit(entry['american_odds']) if entry['outcome'] else -1.)
        if entry['role_probability'] is not None:
            y = int(entry['outcome'])
            brier_differences[entry['game_id']].append((entry['role_probability']-y)**2
                -(entry['market_probability']-y)**2)
    wins = sum(entry['outcome'] for entry in decided)
    values = [v for group in returns.values() for v in group]
    return dict(selected=len(entries), upcoming=sum(utc_timestamp(e['game_start_time']) > now for e in entries),
        pending=len(entries)-len(decided), decided=len(decided), wins=wins,
        distinct_decided_games=len(games), win_rate=wins/len(decided) if decided else None,
        win_rate_game_cluster_95=search.frozen.cluster_interval(games),
        flat_stake_roi=mean(values) if values else None,
        roi_game_cluster_95=search.frozen.cluster_interval(returns),
        candidate_minus_market_brier=mean(v for group in brier_differences.values() for v in group) if brier_differences else None,
        brier_difference_game_cluster_95=search.frozen.cluster_interval(brier_differences),
        mean_recorded_probability=mean(e['probability'] for e in decided) if decided else None,
        mean_role_probability=mean(e['role_probability'] for e in decided) if decided else None,
        mean_matching_market_probability=mean(e['market_probability'] for e in decided) if decided else None)


def audit(receipts, predictions, now):
    require_matching_runtime()
    if len({r['prediction_id'] for r in predictions}) != len(predictions):
        raise ValueError('Duplicate prediction identity')
    verified = paper.audit_receipts(receipts, predictions, 'nfl', 'raw_model', now)
    result = dict(protocol=PROTOCOL, source_audit=verified, observed_at=now.isoformat(),
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        rushing_implementation_sha256=rush.implementation_sha256(),
        status='collecting', promote=False, target_verified=False,
        selections=[], coverage={}, rule={})
    if verified['invalid_receipts']:
        result['status'] = 'invalid_source_evidence'
        return result
    by_id = {row['prediction_id']: row for row in predictions}
    original = []; agreement = []; missing = Counter()
    for receipt in receipts:
        if receipt['sport'] != 'nfl' or receipt['protocol'] != paper.PROTOCOL['policies']['raw_model']:
            continue
        recorded = utc_timestamp(str(receipt['recorded_at']))
        if recorded < utc_timestamp(PROTOCOL['frozen_at']):
            continue
        selection = json.loads(receipt['payload'])['selection']
        if selection['prop_type'] != rush.MARKET:
            continue
        row = by_id[receipt['prediction_id']]
        candidate = row.get('rushing_role_shadow')
        probability = rush.verified_shadow_probability(row)
        if (probability is not None and
                utc_timestamp(candidate['generated_at']) > recorded):
            probability = None
        if probability is None:
            reason = candidate.get('reason') if isinstance(candidate, dict) else None
            missing[reason if isinstance(reason, str) and reason in rush.REASONS else 'missing_or_invalid_candidate'] += 1
        outcome = search.frozen.audit._verified_outcome(row)
        if (type(outcome) is not bool or utc_timestamp(row['outcome_observed_at']) > now
                or utc_timestamp(row['game_start_time']) > now):
            outcome = None
        detail = dict(selection, role_probability=probability, outcome=outcome,
            original_75=selection['probability'] >= PROTOCOL['original_probability_floor'],
            agreement_75=selection['probability'] >= PROTOCOL['original_probability_floor']
                and probability is not None and probability >= PROTOCOL['rushing_role_probability_floor'])
        result['selections'].append(detail)
        if detail['original_75']:
            original.append(detail)
        if detail['agreement_75']:
            agreement.append(detail)
    summary = summarize(agreement, now)
    interval = summary['win_rate_game_cluster_95']
    roi_interval = summary['roi_game_cluster_95']
    brier_interval = summary['brier_difference_game_cluster_95']
    enough = (summary['decided'] >= PROTOCOL['minimum_decisions']
              and summary['distinct_decided_games'] >= PROTOCOL['minimum_distinct_games'])
    result.update(coverage=dict(original_rushing_selections=len(result['selections']),
        original_75=len(original), original_75_with_candidate=sum(e['role_probability'] is not None for e in original),
        unavailable_reasons=dict(missing)), original_75=summarize(original, now), rule=summary,
        evidence_criteria_met=bool(enough and summary['win_rate'] is not None and summary['win_rate'] >= .75
            and interval and interval[0] >= .75 and roi_interval and roi_interval[0] > 0
            and brier_interval and brier_interval[1] < 0),
        limitations=['One fixed prospective 75% agreement rule, with no later pick or price substitution.',
            'Private hypothetical paper picks, not accepted dashboard picks, bets, or a production policy.',
            'Source completeness and candidate probability are reverified from the committed pregame inputs.',
            'A descriptive or favorable early result cannot establish an edge. Review is required after the fixed minimum cohort.'])
    result['status'] = 'review_required' if result['evidence_criteria_met'] else 'awaiting_fixed_cohort' if not enough else 'evidence_not_demonstrated'
    return result



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True,
                        help='Private read-only export with receipts and predictions')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require_matching_runtime()
    evidence = json.loads(args.inputs.read_text(encoding='utf-8'))
    report = audit(evidence['receipts'], evidence['predictions'], datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print('Private prospective rushing-role audit completed')


if __name__ == '__main__':
    main()
