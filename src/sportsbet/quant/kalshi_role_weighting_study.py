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
from sportsbet.quant import kalshi_stat_only_next_series as series
from sportsbet.quant import kalshi_stat_only_remote_anchor as anchor
from sportsbet.quant.kalshi_market_settlement import venue_results
from sportsbet.quant.kalshi_stat_only_forward_eval import _loss

VERSION = 'kalshi-nfl-prospective-role-capped-prior-v1'
START = '2026-10-08T17:00:00+00:00'
POLICY = dict(protocol=VERSION, validation_starts_at=START, sample_games=20,
              original_prior_strength=20, capped_prior_strength=8,
              prior_strength_rule='min(8, older_games + 1)',
              minimum_independent_paired_games=50, maximum_quote_age_seconds=300,
              primary_scope='all original role forecasts; no prop or probability selection',
              comparators=['market', 'prior20', 'role20'],
              metrics=['brier', 'log_loss'], clusters=['game', 'player'])
STAMP = re.compile(r'next-nfl-stat-only-([0-9]{8}T[0-9]{4})\Z')


def implementation() -> str:
    names = ('kalshi_role_weighting_study.py', 'nfl_recent_role_params.py',
             'kalshi_role_shadow.py', 'kalshi_role_shadow_v2.py',
             'kalshi_role_shadow_v4.py', 'kalshi_role_shadow_eval.py',
             'kalshi_stat_only_forward_eval.py', 'kalshi_stat_only_next_series.py',
             'kalshi_market_cohort.py', 'kalshi_pair_capture.py',
             'kalshi_market_settlement.py', 'kalshi_stat_only_next_eval.py',
             'kalshi_stat_only_remote_anchor.py', 'kalshi_pair_series_eval.py')
    hashes = {}
    for name in names:
        path = Path(__file__).resolve().with_name(name)
        if path.is_symlink() or not path.is_file():
            raise ValueError('Role study implementation missing or linked')
        hashes[name] = hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    return digest(hashes)


def probabilities(row: dict) -> dict:
    """Recover exact hit counts from the authenticated original role receipt."""
    n, current, older = (row[k] for k in ('sample_games', 'current_team_games', 'older_games'))
    if (any(type(v) is not int for v in (n, current, older))
            or n != 20 or current + older != n or not 2 <= current <= 19):
        raise ValueError('Original role sample cannot support capped-prior comparison')
    role = Decimal(str(row['model_over_probability']))
    prior = Decimal(str(row['prior20_over_probability']))
    if not all(p.is_finite() and 0 < p < 1 for p in (role, prior)):
        raise ValueError('Original role probability invalid')
    total_raw = prior * (n + 1) - Decimal('.5')
    total = int(round(total_raw))
    current_raw = (role * (current + 20) * (older + 1)
                   - 20 * (Decimal(total) + Decimal('.5'))) / (older + 1 - 20)
    hits = int(round(current_raw))
    old_hits = total - hits
    if (abs(total_raw - total) > Decimal('1e-8')
            or abs(current_raw - hits) > Decimal('1e-8')
            or not 0 <= hits <= current or not 0 <= old_hits <= older):
        raise ValueError('Original role empirical counts cannot be reproduced')
    old_probability = (Decimal(old_hits) + Decimal('.5')) / (older + 1)
    if abs((hits + 20 * old_probability) / (current + 20) - role) > Decimal('1e-8'):
        raise ValueError('Original role strength20 formula changed')
    strength = min(8, older + 1)
    return dict(capped8=str((hits + strength * old_probability) / (current + strength)),
                prior20=str(prior), role20=str(role), current_games=current,
                older_games=older, current_hits=hits, older_hits=old_hits,
                prior_strength=strength, current_weight=str(Decimal(current)/(current + strength)))


def freeze(pair: dict, *, now: datetime) -> dict:
    cohort, role = unpack(pair)
    offers = {r['ticker']: r for r in cohort['selections']}
    rows = role['forecasts']
    if (now.utcoffset() is None or not clock(START) <= clock(pair['started_at'])
            <= clock(pair['completed_at']) <= now
            or now >= min(clock(r['scheduled_game_start_time']) for r in offers.values())
            or role['protocol'] != original.VERSION
            or len(offers) != len(cohort['selections'])
            or len({r['ticker'] for r in rows}) != len(rows)
            or digest(rows) != role['forecasts_sha256']):
        raise ValueError('Role study needs an unchanged new prospective pair')
    ages = [(now - clock(r['received_at'])).total_seconds() for r in offers.values()]
    if not ages or not all(0 <= age <= 300 for age in ages):
        raise ValueError('Role study model/market comparison is not contemporaneous')
    forecasts = []
    for row in rows:
        offer = offers.get(row['ticker'])
        if offer is None or any(row[key] != offer[key] for key in
                ('line', 'milestone_id', 'player_target_id', 'prop_type')):
            raise ValueError('Role study forecast contract changed')
        midpoint = Decimal(str(row['market_yes_midpoint']))
        if (not midpoint.is_finite() or not 0 < midpoint < 1
                or midpoint != Decimal(str(offer['market_midpoint']))):
            raise ValueError('Role study original midpoint changed')
        forecasts.append(dict(ticker=row['ticker'], game=row['milestone_id'],
            player=row['gsis_player_id'], prop_type=row['prop_type'], market=str(midpoint),
            **probabilities(row)))
    return dict(protocol=VERSION, recorded_at=now.isoformat(), policy=POLICY.copy(),
                implementation_sha256=implementation(), pair_sha256=digest(pair),
                original_selected_contracts=len(offers), original_role_forecasts=len(rows),
                original_role_unavailable=len(offers)-len(rows), forecasts=forecasts,
                original_unavailable_reasons=role['unavailable_reasons'],
                edge_established=False, qualified_picks=0, execution_ready=False)


def marker_path(root: Path) -> Path:
    match = STAMP.fullmatch(root.name)
    if match is None:
        raise ValueError('Unexpected prospective role capture name')
    return Path('docs/verification') / f'next-nfl-role-weighting-{match[1]}-anchor.json'


def marker(receipt: dict, commitment: dict) -> dict:
    return dict(protocol=VERSION, role_receipt_sha256=digest(receipt),
                commitment_sha256=digest(commitment), recorded_at=receipt['recorded_at'],
                first_selected_start_at=commitment['first_selected_start_at'])


def prepare(root: Path, values: dict, commitment: dict) -> tuple[Path, dict]:
    receipt, _ = series.single._input(root / 'role-weighting.json', 500_000)
    if freeze(values['pair'], now=clock(receipt['recorded_at'])) != receipt:
        raise ValueError('Prospective role receipt, policy or implementation changed')
    if clock(receipt['recorded_at']) > clock(commitment['committed_at']):
        raise ValueError('Role receipt was not frozen during original collection')
    return marker_path(root), marker(receipt, commitment)


def verify_marker(receipt: dict, commitment: dict, oid: str, primary_path: str) -> dict:
    proof = anchor.verify(commitment, oid, primary_path)
    name = Path(primary_path).name.removesuffix('-anchor.json')
    saved = json.loads(anchor._run('git', 'show', f'{oid}:{marker_path(Path(name)).as_posix()}'))
    if (saved != marker(receipt, commitment)
            or clock(receipt['recorded_at']) > clock(proof['remote_pushed_at'])):
        raise ValueError('Role study marker changed or was not server-published pregame')
    return proof


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
    return dict(protocol=VERSION, policy=POLICY.copy(), captures=len(cases),
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
            or manifest['protocol'] != VERSION
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
