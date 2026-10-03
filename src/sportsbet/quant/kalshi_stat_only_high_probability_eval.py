"""Separate predeclared 75% diagnostic for the pinned NFL stat-only paper cohort.

This does not revise the frozen primary evaluator, collect prices, or place orders.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from sportsbet.quant import kalshi_stat_only_forward_eval as frozen
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_market_settlement import venue_results
from sportsbet.quant.kalshi_pair_capture import unpack


VERSION = 'kalshi-nfl-stat-only-high-probability-diagnostic-v1'
THRESHOLD = Decimal('0.75')


def evaluate(pair: dict, original: dict, forecast: dict, quotes: dict,
             decisions: dict, source_dir: Path, schedule_path: Path,
             settlements: dict | None = None, *, now: datetime | None = None) -> dict:
    """Keep the original policy denominator and score only its fixed p>=.75 subset."""
    pre, _ = frozen.preflight(pair, original, forecast, quotes, decisions,
                              source_dir, schedule_path)
    selected = []
    for row in decisions['candidates']:
        probability = Decimal(str(row['model_win_probability']))
        ask = Decimal(str(row['displayed_ask']))
        if (not probability.is_finite() or not 0 < probability < 1
                or not ask.is_finite() or not 0 < ask < 1):
            raise ValueError('Invalid frozen probability or displayed ask')
        if probability >= THRESHOLD:
            selected.append(row)
    if len(decisions['candidates']) != pre['paper_candidates']:
        raise ValueError('Frozen candidate denominator changed')
    count = len(selected)
    report = dict(protocol=VERSION, primary_protocol=frozen.VERSION,
        original_market_contracts=pre['original_market_contracts'],
        primary_paper_candidates=pre['paper_candidates'],
        threshold=str(THRESHOLD), paper_candidates=count,
        paper_games=len({row['milestone_id'] for row in selected}),
        selected_tickers_sha256=digest(sorted(row['ticker'] for row in selected)),
        mean_frozen_model_win_probability=str(sum(
            Decimal(str(row['model_win_probability'])) for row in selected)/count)
            if count else None,
        mean_displayed_ask=str(sum(
            Decimal(str(row['displayed_ask'])) for row in selected)/count)
            if count else None,
        first_eligible_settlement_at=pre['first_eligible_settlement_at'],
        result_counts=None, verified_candidates=0, verified_games=0,
        verified_wins=0, verified_subset_win_rate=None,
        full_group_win_rate=None, verified_subset_gross_unit_profit=None,
        full_group_gross_unit_profit=None, roi=None, clv=None,
        edge_established=False, qualified_picks=0, execution_ready=False)
    if settlements is None:
        return report
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None or now < clock(pre['first_eligible_settlement_at']):
        raise ValueError('Exact result audit is premature')
    cohort, _ = unpack(pair)
    selection, states = venue_results(original, cohort, settlements, now=now)
    if len(selection) != pre['original_market_contracts'] or len(states) != len(selection):
        raise ValueError('Original exact-contract result denominator changed')
    counts = Counter()
    wins = 0
    paid = Decimal(0)
    verified_games = set()
    for row in selected:
        state, outcome = states[row['ticker']]
        counts[state] += 1
        if state == 'venue_verified':
            verified_games.add(row['milestone_id'])
            wins += int(outcome == row['side'])
            paid += Decimal(str(row['displayed_ask']))
    verified = counts['venue_verified']
    report.update(result_counts=dict(sorted(counts.items())),
        verified_candidates=verified, verified_games=len(verified_games),
        verified_wins=wins,
        verified_subset_win_rate=str(Decimal(wins)/verified) if verified else None,
        full_group_win_rate=str(Decimal(wins)/count)
            if count and verified == count else None,
        verified_subset_gross_unit_profit=str(Decimal(wins)-paid)
            if verified else None,
        full_group_gross_unit_profit=str(Decimal(wins)-paid)
            if count and verified == count else None,
        settlement_evidence_sha256=settlements['evidence_sha256'])
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair', 'market', 'forecast', 'quotes', 'decisions'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--settlements', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Output already exists')
    pair, market, forecast, quotes, decisions = (
        frozen._pinned(getattr(args, name), name) for name in
        ('pair', 'market', 'forecast', 'quotes', 'decisions'))
    settlements = None
    if args.settlements:
        path = args.settlements
        if (path.is_symlink() or not path.is_file()
                or not 0 < path.stat().st_size <= 30_000_000):
            parser.error('Settlement receipt missing or unbounded')
        settlements = json.loads(path.read_text(encoding='utf-8'))
    report = evaluate(pair, market, forecast, quotes, decisions,
                      args.source_dir, args.schedule, settlements)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
