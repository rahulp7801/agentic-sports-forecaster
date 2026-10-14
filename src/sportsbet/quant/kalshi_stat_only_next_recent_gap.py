"""Prospective replication of the fixed five-point recent-history hypothesis.

October 4 motivated this follow-up; it cannot enter this new validation sample.
No primary selection, model probability, price or consumer gate is changed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_stat_only_recent_gap import membership, UPLIFT

VERSION = 'kalshi-nfl-stat-only-next-recent-gap-v1'
LABELS = ('model_uplift_ge_5pp', 'other')
POLICY = dict(protocol=VERSION, chosen_side_uplift=str(UPLIFT),
              validation_starts_at='2026-10-08T17:00:00+00:00',
              minimum_independent_paired_games=50,
              comparators=['market', 'strict_prior20'],
              metrics=['brier', 'log_loss'], clusters=['game', 'player'])


def implementation_hash() -> str:
    files = ('kalshi_stat_only_next_recent_gap.py', 'kalshi_stat_only_recent_gap.py',
             'kalshi_stat_only_next_series.py', 'kalshi_stat_only_forward_eval.py',
             'kalshi_role_shadow_eval.py', 'kalshi_stat_only_win_uncertainty.py')
    hashes = {}
    for name in files:
        path = Path(__file__).resolve().with_name(name)
        if path.is_symlink() or not path.is_file():
            raise ValueError('Replication implementation missing or linked')
        # Git's Windows checkout converts line endings; semantic source bytes
        # must have the same identity before and after staging on this host.
        hashes[name] = hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    return digest(hashes)


def freeze(forecast: dict, decisions: dict, control: dict) -> dict:
    if clock(decisions['decided_at']) < clock(POLICY['validation_starts_at']):
        raise ValueError('Recent-gap follow-up cannot use the motivating cohort')
    forecasts = {row['ticker']: row for row in forecast['forecasts']}
    priors = {row['ticker']: row for row in control['forecast_rows']}
    candidates = decisions['candidates']
    if (len(forecasts) != len(forecast['forecasts'])
            or len(priors) != len(control['forecast_rows'])
            or set(priors) != set(forecasts)
            or len(candidates) != decisions['candidates_count']
            or len({row['ticker'] for row in candidates}) != len(candidates)
            or digest(candidates) != decisions['candidates_sha256']):
        raise ValueError('Recent-gap fixed input scope changed')
    groups = {label: [] for label in LABELS}
    for row in candidates:
        if row['ticker'] not in forecasts:
            raise ValueError('Recent-gap forecast or control missing')
        label = membership(row, forecasts[row['ticker']],
                           Decimal(str(priors[row['ticker']]['prior20_over_probability'])))
        groups[label].append(row['ticker'])
    return dict(protocol=VERSION, policy=deepcopy(POLICY), policy_sha256=digest(POLICY),
                evaluation_implementation_sha256=implementation_hash(),
                original_candidates=len(candidates),
                candidates_sha256=decisions['candidates_sha256'],
                forecast_rows_sha256=digest(forecast['forecasts']),
                control_rows_sha256=digest(control['forecast_rows']),
                groups={label: sorted(rows) for label, rows in groups.items()})


def aggregate(cases: list[dict], *, now: datetime, verify_remote: bool = True) -> dict:
    # Reuse all original source/result/chronology/implementation and remote
    # checks. The primary report supplies its exact earliest-push ownership order.
    from sportsbet.quant import kalshi_stat_only_next_series as primary
    from sportsbet.quant.kalshi_pair_capture import unpack
    from sportsbet.quant.kalshi_market_settlement import venue_results
    from sportsbet.quant.kalshi_stat_only_forward_eval import _loss

    admitted = primary.aggregate(cases, now=now, verify_remote=verify_remote)
    positions = {value: index for index, value in enumerate(admitted['pregame_commitment_sha256'])}
    ordered = sorted(cases, key=lambda case: positions[digest(case['commitment'])])
    seen = set()
    reports = {label: dict(selected=0, games=set(), states=Counter(), quotes=Counter(),
                           wins=0, pairs=[], strict_pairs=[], scores=[]) for label in LABELS}
    for case in ordered:
        if not case['commitment'].get('recent_gap_sha256'):
            raise ValueError('Recent-gap policy was not committed before this cohort')
        values, _, prices = primary.single.committed_preflight(
            case['inputs'], Path(case['source_dir']), case['commitment'])
        receipt = freeze(values['forecast'], values['decisions'], values['control'])
        membership_by_ticker = {ticker: label for label, tickers in receipt['groups'].items() for ticker in tickers}
        cohort, _ = unpack(values['pair'])
        fixtures = primary._fixture_map(values['market'], cohort)
        owned = {game for game, fixture in fixtures.items() if fixture not in seen}
        seen.update(fixtures.values())
        _, states = venue_results(values['market'], cohort, case['settlements'], now=now)
        forecasts = {row['ticker']: row for row in values['forecast']['forecasts']}
        priors = {row['ticker']: row for row in values['control']['forecast_rows']}
        for row in values['decisions']['candidates']:
            if row['milestone_id'] not in owned:
                continue
            ticker, side = row['ticker'], row['side']
            item = reports[membership_by_ticker[ticker]]
            item['selected'] += 1
            item['games'].add(fixtures[row['milestone_id']])
            state, outcome = states[ticker]
            price_state, market_over, _, _ = prices[ticker]
            item['states'][state] += 1
            item['quotes'][price_state] += 1
            if state != 'venue_verified':
                continue
            item['wins'] += int(outcome == side)
            if price_state != 'two_sided_exact':
                continue
            actual = Decimal(int(outcome == side))
            model = _loss(Decimal(str(row['model_win_probability'])), actual)
            prior_over = Decimal(str(priors[ticker]['prior20_over_probability']))
            prior = _loss(prior_over if side == 'yes' else 1-prior_over, actual)
            market = _loss(market_over if side == 'yes' else 1-market_over, actual)
            identity = (str(fixtures[row['milestone_id']]), forecasts[ticker]['gsis_player_id'])
            item['pairs'].append((*identity, model[0]-market[0], model[1]-market[1]))
            item['strict_pairs'].append((*identity, model[0]-prior[0], model[1]-prior[1]))
            item['scores'].append((model, market, prior))
    result = {}
    for label, item in reports.items():
        n = len(item['pairs'])
        games = len({row[0] for row in item['pairs']})
        clustered = games >= 2 and len({row[1] for row in item['pairs']}) >= 2
        bounds = dict(market=primary._bounds(item['pairs'], 'market') if clustered else {},
                      strict_prior20=primary._bounds(item['strict_pairs'], 'strict_prior20') if clustered else {})
        complete = (item['selected'] > 0 and n == item['selected'])
        results_complete = (item['selected'] > 0 and
                            item['states']['venue_verified'] == item['selected'])
        result[label] = dict(frozen_candidates=item['selected'], independent_games=len(item['games']),
            result_states=dict(sorted(item['states'].items())), quote_states=dict(sorted(item['quotes'].items())),
            verified_subset_wins=item['wins'], verified_subset_candidates=item['states']['venue_verified'],
            full_win_rate=str(Decimal(item['wins'])/item['selected']) if results_complete else None,
            results_complete=results_complete,
            paired_results=n, paired_independent_games=games, complete=complete,
            paired_brier={name: str(sum(row[index][0] for row in item['scores'])/n) if n else None
                          for index, name in enumerate(('model', 'market', 'strict_prior20'))},
            paired_bounds=bounds,
            replication_supported=bool(complete and admitted['remote_pregame_anchor_verified']
                and games >= POLICY['minimum_independent_paired_games']
                and all(primary._favorable(bounds[name], name) for name in bounds)))
    return dict(protocol=VERSION, policy_sha256=digest(POLICY),
        evaluation_implementation_sha256=implementation_hash(), groups=result,
        pregame_commitment_sha256=admitted['pregame_commitment_sha256'],
        duplicate_games_excluded=admitted['duplicate_games_excluded'],
        independent_selected_games=admitted['independent_selected_games'],
        remote_pregame_anchor_verified=admitted['remote_pregame_anchor_verified'],
        edge_established=False, qualified_picks=0, execution_ready=False,
        fills_verified=False, fees_verified=False, roi=None, clv=None)


def main() -> None:
    from sportsbet.quant import kalshi_stat_only_next_series as primary

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Replication output already exists')
    manifest, _ = primary.single._input(args.manifest, 100_000)
    if (manifest.get('protocol') != VERSION or
            not 0 < len(manifest.get('cases', [])) <= primary.MAX_CASES):
        parser.error('Invalid private replication manifest')
    root = args.manifest.resolve().parent
    cases = []
    for row in manifest['cases']:
        if set(row) != set(primary.single.LIMITS) | {
                'source_dir', 'commitment', 'settlements',
                'anchor_commit_oid', 'anchor_marker_path'}:
            parser.error('Invalid replication case path scope')
        inputs = {name: str(primary._local(root, row[name])) for name in primary.single.LIMITS}
        commitment, _ = primary.single._input(primary._local(root, row['commitment']), 10_000)
        settlements, _ = primary.single._input(primary._local(root, row['settlements']), 30_000_000)
        cases.append(dict(inputs=inputs, source_dir=primary._local(root, row['source_dir']),
                          commitment=commitment, settlements=settlements,
                          anchor_commit_oid=row['anchor_commit_oid'],
                          anchor_marker_path=row['anchor_marker_path']))
    report = aggregate(cases, now=datetime.now(timezone.utc), verify_remote=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps({key: report[key] for key in (
        'protocol', 'independent_selected_games', 'remote_pregame_anchor_verified',
        'edge_established', 'qualified_picks')}, sort_keys=True))


if __name__ == '__main__':
    main()
