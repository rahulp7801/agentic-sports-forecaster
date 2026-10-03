"""Precommitted, untraded receptions NO tail of the fixed October 4 NFL paper cohort.

This is a separate diagnostic motivated by inspected, unpriced 2025 examples.
It cannot change the original 70 decisions or establish a market edge.
"""
from __future__ import annotations

import argparse
import hashlib
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from sportsbet.quant import kalshi_stat_only_forward_eval as frozen
from sportsbet.quant import kalshi_market_settlement as venue
from sportsbet.quant import kalshi_stat_only_settlement_capture as capture
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_pair_capture import unpack

VERSION = 'kalshi-nfl-stat-only-receptions-no-tail-v1'
THRESHOLD = Decimal('0.75')
EXPECTED_TICKERS_SHA256 = 'ed073d479d79c870a7b11c1bdc81460a89076704572aa48c668e6ec9bd058ee7'
HISTORICAL_TAIL_REPORT_SHA256 = '1ab6e8cfa7f7c660e879a32e11a3aea3679528f4448ad9a4fcedfd7d3e4bdfa3'


def selected_rows(forecast: dict, decisions: dict) -> list[dict]:
    by_ticker = {row['ticker']: row for row in forecast['forecasts']}
    if len(by_ticker) != len(forecast['forecasts']):
        raise ValueError('Duplicate frozen forecast ticker')
    high = [row for row in decisions['candidates']
            if Decimal(str(row['model_win_probability'])) >= THRESHOLD]
    selected = [row for row in high if row['side'] == 'no'
                and by_ticker[row['ticker']]['prop_type'] == 'receptions']
    if (len(high) != 11 or len(selected) != 8
            or digest(sorted(row['ticker'] for row in selected)) != EXPECTED_TICKERS_SHA256):
        raise ValueError('Precommitted receptions tail changed')
    return selected


def evaluate(pair: dict, market: dict, forecast: dict, quotes: dict, decisions: dict,
             source_dir: Path, schedule: Path, settlements: dict | None = None,
             *, now: datetime | None = None) -> dict:
    pre, _ = frozen.preflight(pair, market, forecast, quotes, decisions,
                              source_dir, schedule)
    selected = selected_rows(forecast, decisions)
    count = len(selected)
    report = dict(protocol=VERSION, original_market_contracts=pre['original_market_contracts'],
        original_model_forecasts=pre['model_forecasts'],
        original_paper_candidates=pre['paper_candidates'],
        historical_tail_report_sha256=HISTORICAL_TAIL_REPORT_SHA256,
        selection_rule='original paper candidates: NO, receptions, frozen model p>=0.75',
        selected_tickers_sha256=EXPECTED_TICKERS_SHA256,
        paper_candidates=count, paper_games=len({row['milestone_id'] for row in selected}),
        mean_model_win_probability=str(sum(Decimal(str(row['model_win_probability']))
                                           for row in selected)/count),
        mean_displayed_ask=str(sum(Decimal(str(row['displayed_ask']))
                                   for row in selected)/count),
        first_eligible_settlement_at=pre['first_eligible_settlement_at'],
        result_counts=None, verified_candidates=0, verified_games=0,
        verified_wins=0, verified_subset_win_rate=None, full_group_win_rate=None,
        verified_subset_gross_unit_profit=None, full_group_gross_unit_profit=None,
        fills_verified=False, fees_verified=False, roi=None, clv=None,
        edge_established=False, qualified_picks=0, execution_ready=False)
    if settlements is None:
        return report
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None or now < clock(pre['first_eligible_settlement_at']):
        raise ValueError('Exact result audit is premature')
    if (settlements.get('protocol') != capture.VERSION
            or settlements.get('record_sha256') != digest({k:v for k,v in settlements.items()
                                                            if k != 'record_sha256'})):
        raise ValueError('Unsigned venue receipt integrity failed')
    cohort, _ = unpack(pair)
    selection, states = venue.venue_results(market, cohort, settlements, now=now)
    if len(selection) != pre['original_market_contracts'] or len(states) != len(selection):
        raise ValueError('Original venue denominator changed')
    counts = Counter()
    wins = 0
    paid = Decimal(0)
    games = set()
    for row in selected:
        state, outcome = states[row['ticker']]
        counts[state] += 1
        if state == 'venue_verified':
            games.add(row['milestone_id'])
            wins += int(outcome == 'no')
            paid += Decimal(str(row['displayed_ask']))
    verified = counts['venue_verified']
    report.update(result_counts=dict(sorted(counts.items())),
        verified_candidates=verified, verified_games=len(games), verified_wins=wins,
        verified_subset_win_rate=str(Decimal(wins)/verified) if verified else None,
        full_group_win_rate=str(Decimal(wins)/count) if verified == count else None,
        verified_subset_gross_unit_profit=str(Decimal(wins)-paid) if verified else None,
        full_group_gross_unit_profit=str(Decimal(wins)-paid) if verified == count else None,
        settlement_evidence_sha256=settlements['evidence_sha256'])
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair', 'market', 'forecast', 'quotes', 'decisions'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--historical-tail', type=Path, required=True)
    parser.add_argument('--settlements', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Diagnostic output already exists')
    tail_bytes = args.historical_tail.read_bytes()
    if (not 0 < len(tail_bytes) <= 100_000
            or hashlib.sha256(tail_bytes).hexdigest() != HISTORICAL_TAIL_REPORT_SHA256):
        parser.error('Pinned historical tail report changed')
    pair, market, forecast, quotes, decisions = (
        frozen._pinned(getattr(args, name), name) for name in
        ('pair', 'market', 'forecast', 'quotes', 'decisions'))
    settlements = None
    if args.settlements:
        if not 0 < args.settlements.stat().st_size <= venue.MAX_INPUT_BYTES:
            parser.error('Venue receipt exceeds size bound')
        settlements = json.loads(args.settlements.read_text(encoding='utf-8'))
    result = evaluate(pair, market, forecast, quotes, decisions,
                      args.source_dir, args.schedule, settlements)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()