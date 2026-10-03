"""Outcome-blind game-cluster uncertainty plan for two fixed NFL paper groups.

Runs only after the full exact-contract venue result gate. No network, fills,
consumer picks, model changes, or outcome-dependent candidate selection.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import random
import re

from sportsbet.quant import kalshi_market_settlement as venue
from sportsbet.quant import kalshi_stat_only_prelock_paper_result as paper
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_pair_capture import unpack
from sportsbet.quant.kalshi_stat_only_forward_eval import _pinned, preflight
from sportsbet.quant.kalshi_stat_only_prelock_fee_score import _receipt

VERSION = 'kalshi-nfl-stat-only-fixed-win-uncertainty-v1'
SAMPLES = 10_000
SEED = 20261004
HIGH_PROBABILITY = Decimal('.75')


def _interval(rows: list[tuple[str, int]]) -> dict:
    """Resample whole games; retain all correlated candidate rows per draw."""
    by_game: dict[str, list[int]] = defaultdict(list)
    for game, win in rows:
        by_game[game].append(win)
    games = [(game, sum(wins), len(wins)) for game, wins in sorted(by_game.items())]
    rng = random.Random(SEED)
    contract_draws, equal_game_draws = [], []
    for _ in range(SAMPLES):
        draw = [games[rng.randrange(len(games))] for _ in games]
        contract_draws.append(sum(win for _, win, _ in draw) /
                              sum(count for _, _, count in draw))
        equal_game_draws.append(sum(win/count for _, win, count in draw) / len(draw))
    contract_draws.sort()
    equal_game_draws.sort()
    lower, upper = int(SAMPLES*.025), int(SAMPLES*.975)
    return {'contract_weighted_95': [format(contract_draws[lower], '.6f'),
                                     format(contract_draws[upper], '.6f')],
            'equal_game_95': [format(equal_game_draws[lower], '.6f'),
                              format(equal_game_draws[upper], '.6f')]}


def evaluate(decisions: dict, states: dict[str, tuple[str, str | None]],
             *, settlement_sha256: str) -> dict:
    candidates = decisions['candidates']
    if (len(candidates) != 70 or decisions.get('candidates_count') != 70
            or digest(candidates) != decisions.get('candidates_sha256')
            or len({row['ticker'] for row in candidates}) != 70
            or decisions.get('candidate_games') != 15
            or len({row['milestone_id'] for row in candidates}) != 15):
        raise ValueError('Frozen 70-candidate, 15-game commitment changed')
    if not isinstance(settlement_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', settlement_sha256):
        raise ValueError('Venue settlement commitment missing')
    selected = []
    for row in candidates:
        probability = Decimal(str(row['model_win_probability']))
        if (row['side'] not in ('yes', 'no') or not probability.is_finite()
                or not 0 < probability < 1):
            raise ValueError('Frozen candidate probability or side invalid')
        if probability >= HIGH_PROBABILITY:
            selected.append(row)
    if len(selected) != 11 or len({row['milestone_id'] for row in selected}) != 8:
        raise ValueError('Predeclared 11-candidate, eight-game diagnostic changed')
    reports = {}
    for label, fixed in [('all_70', candidates), ('model_p_at_least_75', selected)]:
        observed: list[tuple[str, int]] = []
        fully_verified_games: dict[str, bool] = defaultdict(lambda: True)
        for row in fixed:
            ticker, game = row['ticker'], row['milestone_id']
            if ticker not in states:
                raise ValueError('Venue states missed a frozen candidate')
            state, outcome = states[ticker]
            if state == 'venue_verified':
                if outcome not in ('yes', 'no'):
                    raise ValueError('Verified venue result is not binary')
                observed.append((game, int(outcome == row['side'])))
            else:
                if outcome is not None:
                    raise ValueError('Unverified venue result carries an outcome')
                fully_verified_games[game] = False
            if game not in fully_verified_games:
                fully_verified_games[game] = True
        full = len(observed) == len(fixed)
        wins = sum(win for _, win in observed)
        report = {'frozen_candidates': len(fixed),
                  'frozen_games': len({row['milestone_id'] for row in fixed}),
                  'verified_subset_candidates': len(observed),
                  'verified_subset_games': len({game for game, _ in observed}),
                  'fully_verified_games': sum(fully_verified_games.values()),
                  'missing_or_unverified_candidates': len(fixed)-len(observed),
                  'verified_subset_wins': wins,
                  'verified_subset_win_rate': str(Decimal(wins)/len(observed))
                      if observed else None,
                  'complete': full,
                  'full_win_rate': str(Decimal(wins)/len(fixed)) if full else None,
                  'full_equal_game_win_rate': str(sum(
                      Decimal(sum(win for game, win in observed if game == game_id)) /
                      sum(game == game_id for game, _ in observed)
                      for game_id in {game for game, _ in observed}) /
                      len({game for game, _ in observed})) if full else None,
                  'full_game_cluster_95': _interval(observed) if full else None}
        reports[label] = report
    return {'protocol': VERSION, 'candidate_rows_sha256': decisions['candidates_sha256'],
            'settlement_evidence_sha256': settlement_sha256,
            'high_probability_threshold': str(HIGH_PROBABILITY),
            'resampling': f'{SAMPLES} deterministic whole-game draws, seed {SEED}',
            'groups': reports, 'actual_fills_verified': False,
            'roi': None, 'repeatable_edge_established': False,
            'qualified_picks': 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair', 'market', 'forecast', 'quotes', 'decisions'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--settlements', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Uncertainty output already exists')
    pair, market, forecast, quotes, decisions = (
        _pinned(getattr(args, name), name) for name in
        ('pair', 'market', 'forecast', 'quotes', 'decisions'))
    pre, _ = preflight(pair, market, forecast, quotes, decisions,
                       args.source_dir, args.schedule)
    now = datetime.now(timezone.utc)
    if now < clock(pre['first_eligible_settlement_at']):
        parser.error('Before full-cohort result gate; no settlement input read')
    settlement = _receipt(args.settlements)
    paper.verify_capture_wrapper(settlement, pre)
    cohort, _ = unpack(pair)
    _, states = venue.venue_results(market, cohort, settlement, now=now)
    report = evaluate(decisions, states,
                      settlement_sha256=settlement['evidence_sha256'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
