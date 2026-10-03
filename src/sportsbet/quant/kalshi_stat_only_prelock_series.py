"""No-network full-denominator audit of fixed NFL stat-only prelock receipts."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_stat_only_forward_eval import _pinned, preflight
from sportsbet.quant.kalshi_stat_only_prelock import (
    EARLIEST, LATEST, evaluate as evaluate_group, scope,
)

VERSION = 'kalshi-nfl-stat-only-prelock-series-v1'
MAX_RECEIPT_BYTES = 10_000_000


def evaluate(original: dict, forecast: dict, decisions: dict,
             receipts: list[dict], *, now: datetime) -> dict:
    """A missing future window stays pending; a closed window stays missing."""
    if now.utcoffset() is None:
        raise ValueError('Audit clock must be timezone aware')
    kickoffs = sorted({clock(row['scheduled_game_start_time'])
                       for row in forecast['forecasts']})
    groups = {kickoff: scope(forecast, decisions, kickoff)[0] for kickoff in kickoffs}
    if sum(map(len, groups.values())) != decisions['candidates_count']:
        raise ValueError('Frozen paper denominator changed')
    by_kickoff = {}
    for receipt in receipts:
        kickoff = clock(receipt['evidence']['kickoff'])
        if kickoff not in groups or kickoff in by_kickoff:
            raise ValueError('Unselected or duplicate prelock capture')
        if clock(receipt['evidence']['captured_at']) > now:
            raise ValueError('Prelock receipt occurs after audit clock')
        by_kickoff[kickoff] = receipt
    states = Counter()
    group_rows = []
    matched = games = up = down = unchanged = 0
    contract_total = game_total = Decimal(0)
    for kickoff, candidates in groups.items():
        receipt = by_kickoff.get(kickoff)
        if receipt is None:
            state = ('not_yet_due' if now < kickoff-EARLIEST else
                     'window_open' if now < kickoff-LATEST else 'missed_capture')
            states[state] += len(candidates)
            group_rows.append(dict(kickoff=kickoff.isoformat(), frozen_candidates=len(candidates),
                                   capture_state=state, matched_candidates=0,
                                   receipt_sha256=None))
            continue
        report = evaluate_group(original, forecast, decisions, receipt)
        states.update(report['candidate_state_counts'])
        matched += report['matched_candidates']
        games += report['matched_games']
        up += report['side_ask_up']
        down += report['side_ask_down']
        unchanged += report['side_ask_unchanged']
        if report['mean_side_ask_change'] is not None:
            contract_total += Decimal(report['mean_side_ask_change'])*report['matched_candidates']
            game_total += Decimal(report['equal_game_mean_side_ask_change'])*report['matched_games']
        group_rows.append(dict(kickoff=kickoff.isoformat(), frozen_candidates=len(candidates),
            capture_state='observed', matched_candidates=report['matched_candidates'],
            receipt_sha256=report['later_receipt_sha256'],
            candidate_state_counts=report['candidate_state_counts']))
    if sum(states.values()) != decisions['candidates_count'] or matched != up+down+unchanged:
        raise AssertionError('Full prelock denominator changed')
    return dict(protocol=VERSION, audited_at=now.isoformat(),
        forecast_sha256=forecast['forecast_sha256'],
        candidates_sha256=decisions['candidates_sha256'],
        frozen_candidates=decisions['candidates_count'], frozen_kickoff_groups=len(groups),
        observed_kickoff_groups=len(by_kickoff), full_candidate_state_counts=dict(sorted(states.items())),
        group_state_rows_sha256=digest(group_rows), groups=group_rows,
        matched_candidates=matched, matched_games=games,
        complete_markout=matched==decisions['candidates_count'],
        side_ask_up=up, side_ask_down=down, side_ask_unchanged=unchanged,
        mean_side_ask_change=str(contract_total/matched) if matched else None,
        equal_game_mean_side_ask_change=str(game_total/games) if games else None,
        actual_fills_verified=False, closing_line_verified=False,
        edge_established=False, qualified_picks=0, roi=None, clv=None,
        execution_ready=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair', 'market', 'forecast', 'quotes', 'decisions'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Output already exists')
    pair, market, forecast, quotes, decisions = (
        _pinned(getattr(args, name), name) for name in
        ('pair', 'market', 'forecast', 'quotes', 'decisions'))
    preflight(pair, market, forecast, quotes, decisions, args.source_dir, args.schedule)
    if len(args.receipt) > 6 or len(set(args.receipt)) != len(args.receipt):
        parser.error('Duplicate or unbounded prelock receipts')
    receipts = []
    for path in args.receipt:
        if (path.is_symlink() or not path.is_file()
                or not 0 < path.stat().st_size <= MAX_RECEIPT_BYTES):
            parser.error('Prelock receipt missing or unbounded')
        receipts.append(json.loads(path.read_text(encoding='utf-8')))
    report = evaluate(market, forecast, decisions, receipts,
                      now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
