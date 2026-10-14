"""Prospective capped-prior role comparison, separate from frozen consumer models.

The October 4 results motivated this hypothesis and cannot validate it. Use the
same already collected role inputs and contemporaneous midpoint; never request
another quote, replace an unavailable forecast or promote a consumer pick.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_pair_capture import unpack
from sportsbet.quant import kalshi_role_shadow_v4 as original
from sportsbet.quant import kalshi_stat_only_next_series_v2 as series
from sportsbet.quant import kalshi_stat_only_remote_anchor as anchor
from sportsbet.quant.kalshi_market_settlement import venue_results
from sportsbet.quant.kalshi_stat_only_forward_eval import _loss

from sportsbet.quant import kalshi_role_weighting_study as frozen

VERSION = frozen.VERSION
POLICY = frozen.POLICY
EVALUATION_VERSION = 'kalshi-nfl-prospective-capped-role-evaluation-v2'
freeze = frozen.freeze


def evaluation_hash() -> str:
    from sportsbet.quant.kalshi_stat_only_next_teammate_study_v2 import implementation
    return digest(implementation())

prepare = frozen.prepare
verify_marker = frozen.verify_marker


def aggregate(cases: list[dict], *, now: datetime) -> dict:
    # Original source, schedule, quote, frozen model and full-cohort result gates
    # run first. The earliest server-published capture owns the entire fixture.
    admitted = series.aggregate(cases, now=now, verify_remote=True)
    positions = {v: i for i, v in enumerate(admitted['pregame_commitment_sha256'])}
    ordered = sorted(cases, key=lambda case: positions[digest(case['commitment'])])
    seen, states, props = set(), Counter(), Counter()
    selected = forecasted = overlap = 0
    scores = {k: [] for k in ('capped8', 'market', 'prior20', 'role20')}
    differences = {k: [] for k in POLICY['comparators']}
    for case in ordered:
        root = Path(case['inputs']['pair']).parent
        values, _, _ = series.single.committed_preflight(
            case['inputs'], Path(case['source_dir']), case['commitment'])
        receipt, _ = series.single._input(root / 'role-weighting.json', 500_000)
        prepare(root, values, case['commitment'])
        verify_marker(receipt, case['commitment'], case['anchor_commit_oid'], case['anchor_marker_path'])
        cohort, _ = unpack(values['pair'])
        fixtures = series._fixture_map(values['market'], cohort)
        owned = {game for game, fixture in fixtures.items() if fixture not in seen}
        seen.update(fixtures.values())
        selected += sum(r['milestone_id'] in owned for r in cohort['selections'])
        _, results = venue_results(values['market'], cohort, case['settlements'], now=now)
        for row in receipt['forecasts']:
            if row['game'] not in owned:
                overlap += 1
                continue
            forecasted += 1
            status, outcome = results[row['ticker']]
            states[status] += 1
            if status != 'venue_verified':
                continue
            props[row['prop_type']] += 1
            actual = Decimal(int(outcome == 'yes'))
            loss = {key: _loss(Decimal(row[key]), actual) for key in scores}
            for key in scores:
                scores[key].append(loss[key])
            identity = (str(fixtures[row['game']]), row['player'])
            for key in differences:
                differences[key].append((*identity, *(a-b for a,b in zip(loss['capped8'], loss[key], strict=True))))
    n = len(scores['capped8'])
    games = len({r[0] for r in differences['market']})
    players = len({r[1] for r in differences['market']})
    clustered = games >= 2 and players >= 2
    bounds = {key: series._bounds(rows, key) if clustered else {} for key, rows in differences.items()}
    complete = forecasted > 0 and n == forecasted
    supported = complete and games >= 50 and all(series._favorable(bounds[k], k) for k in differences)
    return dict(protocol=EVALUATION_VERSION, frozen_receipt_protocol=VERSION,
        evaluation_implementation_sha256=evaluation_hash(), policy=POLICY.copy(), captures=len(cases),
        original_owned_contracts=selected, owned_role_forecasts=forecasted,
        original_role_unavailable=selected-forecasted, overlap_forecasts_excluded=overlap,
        result_states=dict(states), paired_binary=n, paired_independent_games=games, paired_players=players,
        minimum_50_independent_games_met=games >= 50,
        verified_prop_counts=dict(props), full_forecast_result_coverage=complete,
        paired_scores={key: {metric: str(sum(value[index] for value in entries)/n) if n else None
            for index, metric in enumerate(('brier', 'log_loss'))} for key, entries in scores.items()},
        bounds=bounds, prospective_predictive_improvement_supported=supported,
        remote_pregame_verified=True, market_midpoint_executable=False, edge_established=False,
        qualified_picks=0, execution_ready=False, roi=None, clv=None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Exclusive role study output already exists')
    manifest, _ = series.single._input(args.manifest, 100_000)
    if (not isinstance(manifest, dict) or set(manifest) != {'protocol', 'cases'}
            or manifest['protocol'] != EVALUATION_VERSION
            or not isinstance(manifest['cases'], list)
            or not 0 < len(manifest['cases']) <= series.MAX_CASES):
        parser.error('Role study manifest scope invalid')
    root = args.manifest.resolve().parent
    cases = []
    # Authenticate every original pregame byte and the full settlement time gate
    # before reading result bytes, just as the existing prospective series does.
    for row in manifest['cases']:
        if not isinstance(row, dict) or set(row) != set(series.single.LIMITS) | {
                'source_dir', 'commitment', 'settlements', 'anchor_commit_oid', 'anchor_marker_path'}:
            parser.error('Role study case path scope invalid')
        commitment, _ = series.single._input(series._local(root, row['commitment']), 10_000)
        inputs = {k: str(series._local(root, row[k])) for k in series.single.LIMITS}
        sources = series._local(root, row['source_dir'])
        values, pre, _ = series.single.committed_preflight(inputs, sources, commitment)
        prepare(Path(inputs['pair']).parent, values, commitment)
        receipt, _ = series.single._input(Path(inputs['pair']).parent/'role-weighting.json', 500_000)
        verify_marker(receipt, commitment, row['anchor_commit_oid'], row['anchor_marker_path'])
        if datetime.now(timezone.utc) < clock(pre['first_eligible_settlement_at']):
            raise ValueError('Before original full-cohort settlement gate')
        settlements, _ = series.single._input(series._local(root, row['settlements']), 30_000_000)
        cases.append(dict(inputs=inputs, source_dir=str(sources), commitment=commitment,
            settlements=settlements, anchor_commit_oid=row['anchor_commit_oid'],
            anchor_marker_path=row['anchor_marker_path']))
    report = aggregate(cases, now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
    print(json.dumps({k: report[k] for k in ('protocol', 'paired_binary', 'prospective_predictive_improvement_supported', 'edge_established')}))


if __name__ == '__main__':
    main()
