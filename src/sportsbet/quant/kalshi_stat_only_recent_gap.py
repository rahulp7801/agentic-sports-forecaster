"""Fixed, outcome-blind recent-history disagreement audit for October 4 paper.

The original seventy selections, model and strict last-20 receipt are frozen.
This separate report never selects a contract or promotes a consumer pick.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import re

from sportsbet.quant import kalshi_market_settlement as venue
from sportsbet.quant import kalshi_stat_only_prelock_paper_result as paper
from sportsbet.quant import kalshi_stat_only_prelock_fee_score as fee_score
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_pair_capture import unpack
from sportsbet.quant.kalshi_role_shadow_eval import _forward_bounds
from sportsbet.quant.kalshi_stat_only_forward_eval import _loss, _pinned, preflight
from sportsbet.quant.kalshi_stat_only_prior20_eval import pinned_control

VERSION = 'kalshi-nfl-stat-only-recent-gap-v1'
UPLIFT = Decimal('.05')
GROUP_HASHES = {
    'model_uplift_ge_5pp': '406c4d3bdd3121d3f8778a92a0cd03faa5328fec703b5eff8fe3802e0dc2f966',
    'other': 'd4db3e9b7c7dba1f549922636b83ef2d4f328e93ebbad7a88d75c30c4d218c57',
}
GROUP_COUNTS = {'model_uplift_ge_5pp': 23, 'other': 47}


def membership(candidate: dict, forecast: dict, prior_over: Decimal) -> str:
    """Freeze chosen-side model uplift over strictly prior twenty games."""
    side = candidate['side']
    if side not in ('yes', 'no'):
        raise ValueError('Original decision side invalid')
    model_over = Decimal(str(forecast['model_over_probability']))
    model = Decimal(str(candidate['model_win_probability']))
    prior = prior_over if side == 'yes' else 1-prior_over
    expected = model_over if side == 'yes' else 1-model_over
    if (not all(p.is_finite() and 0 < p < 1 for p in (model_over, model, prior_over, prior))
            or model != expected or candidate['ticker'] != forecast['ticker']
            or candidate['milestone_id'] != forecast['milestone_id']):
        raise ValueError('Original chosen-side model or recent baseline changed')
    return 'model_uplift_ge_5pp' if model-prior >= UPLIFT else 'other'


def fixed_groups(forecast: dict, decisions: dict, control: dict) -> dict[str, list[dict]]:
    candidates = decisions['candidates']
    if (len(candidates) != 70 or decisions.get('candidates_count') != 70
            or decisions.get('candidate_games') != 15
            or digest(candidates) != decisions.get('candidates_sha256')):
        raise ValueError('Original fixed paper cohort changed')
    by_forecast = {row['ticker']: row for row in forecast['forecasts']}
    by_prior = {row['ticker']: Decimal(str(row['prior20_over_probability']))
                for row in control['forecast_rows']}
    if (len(by_forecast) != len(forecast['forecasts'])
            or len(by_prior) != len(control['forecast_rows'])):
        raise ValueError('Duplicate forecast or recent baseline')
    groups: dict[str, list[dict]] = {name: [] for name in GROUP_HASHES}
    for row in candidates:
        ticker = row['ticker']
        if ticker not in by_forecast or ticker not in by_prior:
            raise ValueError('Original selected forecast or baseline missing')
        groups[membership(row, by_forecast[ticker], by_prior[ticker])].append(row)
    if (len({row['ticker'] for row in candidates}) != 70
            or {name: len(rows) for name, rows in groups.items()} != GROUP_COUNTS
            or any(digest(sorted(row['ticker'] for row in rows)) != GROUP_HASHES[name]
                   for name, rows in groups.items())):
        raise ValueError('Pregame recent-gap subgroup changed')
    return groups


def _score_groups(groups: dict[str, list[dict]], forecast: dict, control: dict,
                  prices: dict, states: dict, *, settlement_sha256: str) -> dict:
    if not isinstance(settlement_sha256, str) or not re.fullmatch('[0-9a-f]{64}', settlement_sha256):
        raise ValueError('Authenticated settlement commitment missing')
    by_forecast = {row['ticker']: row for row in forecast['forecasts']}
    by_prior = {row['ticker']: Decimal(str(row['prior20_over_probability']))
                for row in control['forecast_rows']}
    reports = {}
    for label, candidates in groups.items():
        counts = Counter()
        wins = 0
        paired_market, paired_prior = [], []
        scores: dict[str, list[tuple[Decimal, Decimal]]] = {
            'model': [], 'market': [], 'strict_prior20': []}
        for row in candidates:
            ticker, side = row['ticker'], row['side']
            if ticker not in states or ticker not in prices:
                raise ValueError('Fixed candidate result or price missing')
            if membership(row, by_forecast[ticker], by_prior[ticker]) != label:
                raise ValueError('Fixed subgroup membership changed')
            state, outcome = states[ticker]
            counts[state] += 1
            if state != 'venue_verified':
                if outcome is not None:
                    raise ValueError('Unverified outcome is populated')
                continue
            if outcome not in ('yes', 'no'):
                raise ValueError('Verified venue outcome is not binary')
            win = Decimal(int(outcome == side))
            wins += int(win)
            price_state, market_over, _, _ = prices[ticker]
            if price_state != 'two_sided_exact':
                continue
            model = Decimal(str(row['model_win_probability']))
            prior = by_prior[ticker] if side == 'yes' else 1-by_prior[ticker]
            market = market_over if side == 'yes' else 1-market_over
            result = {name: _loss(value, win) for name, value in (
                ('model', model), ('strict_prior20', prior), ('market', market))}
            for name, loss in result.items():
                scores[name].append(loss)
            game, player = row['milestone_id'], by_forecast[ticker]['gsis_player_id']
            paired_market.append((game, player, *(a-b for a, b in zip(
                result['model'], result['market'], strict=True))))
            paired_prior.append((game, player, *(a-b for a, b in zip(
                result['model'], result['strict_prior20'], strict=True))))
        paired = len(paired_market)
        paired_games = len({game for game, _, _, _ in paired_market})
        paired_players = len({player for _, player, _, _ in paired_market})
        interval_ready = paired_games >= 2 and paired_players >= 2
        verified = counts['venue_verified']
        reports[label] = dict(
            fixed_candidates=len(candidates), fixed_games=len({r['milestone_id'] for r in candidates}),
            result_states=dict(sorted(counts.items())), verified_candidates=verified,
            verified_wins=wins, verified_subset_win_rate=str(Decimal(wins)/verified)
                if verified else None,
            complete_results=verified == len(candidates),
            full_win_rate=str(Decimal(wins)/len(candidates))
                if verified == len(candidates) else None,
            same_price_paired_results=paired,
            same_price_paired_games=paired_games,
            same_price_paired_players=paired_players,
            paired_scores={name: {metric: str(sum(row[index] for row in values)/paired)
                if paired else None for index, metric in enumerate(('brier','log_loss'))}
                for name, values in scores.items()},
            model_minus_market_bounds=_forward_bounds(paired_market, 'market')
                if interval_ready else None,
            model_minus_strict_prior20_bounds=_forward_bounds(paired_prior, 'prior20')
                if interval_ready else None)
    return dict(protocol=VERSION, original_fixed_candidates=sum(len(g) for g in groups.values()),
        group_ticker_sha256=GROUP_HASHES, group_threshold=str(UPLIFT), groups=reports,
        settlement_evidence_sha256=settlement_sha256, probability_support=False,
        edge_established=False, qualified_picks=0, fills_verified=False,
        roi=None, clv=None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair', 'market', 'forecast', 'quotes', 'decisions'):
        parser.add_argument('--'+name, type=Path, required=True)
    for name in ('source-dir', 'schedule', 'settlements', 'control', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Recent-gap output already exists')
    pair, market, forecast, quotes, decisions = (
        _pinned(getattr(args, name), name) for name in
        ('pair', 'market', 'forecast', 'quotes', 'decisions'))
    pre, prices = preflight(pair, market, forecast, quotes, decisions,
                            args.source_dir, args.schedule)
    now = datetime.now(timezone.utc)
    if now < clock(pre['first_eligible_settlement_at']):
        parser.error('Before full-cohort result gate; no settlement input read')
    control = pinned_control(args.control, forecast, decisions)
    groups = fixed_groups(forecast, decisions, control)
    settlement = fee_score._receipt(args.settlements)
    paper.verify_capture_wrapper(settlement, pre)
    cohort, _ = unpack(pair)
    selected, states = venue.venue_results(market, cohort, settlement, now=now)
    if len(selected) != pre['original_market_contracts']:
        raise ValueError('Full original venue result denominator changed')
    report = _score_groups(groups, forecast, control, prices, states,
                           settlement_sha256=settlement['evidence_sha256'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps({key: report[key] for key in (
        'protocol','original_fixed_candidates','group_ticker_sha256',
        'edge_established')}, sort_keys=True))


if __name__ == '__main__':
    main()
