"""Offline fee/quote coverage for every frozen NFL stat-only paper candidate.

A full-cohort cost scenario remains unavailable until each fixed kickoff group
has both independent, replayable public receipts. No network or result lookup.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path

from sportsbet.quant import kalshi_stat_only_prelock as prelock
from sportsbet.quant import kalshi_stat_only_prelock_fees as fees
from sportsbet.quant import kalshi_stat_only_prelock_fee_score as fee_score
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_stat_only_forward_eval import _pinned, preflight

VERSION = 'kalshi-nfl-stat-only-prelock-fee-cohort-v1'


def groups(forecast: dict, decisions: dict) -> dict[str, int]:
    starts = {row['ticker']: row['scheduled_game_start_time']
              for row in forecast['forecasts']}
    if len(starts) != len(forecast['forecasts']):
        raise ValueError('Duplicate frozen forecast ticker')
    counts = Counter()
    for row in decisions['candidates']:
        if row['ticker'] not in starts:
            raise ValueError('Candidate missing frozen kickoff')
        counts[clock(starts[row['ticker']]).isoformat()] += 1
    if (len(decisions['candidates']) != decisions['candidates_count']
            or digest(decisions['candidates']) != decisions['candidates_sha256']
            or len(counts) != 6 or sum(counts.values()) != 70):
        raise ValueError('Frozen 70-candidate, six-kickoff scope changed')
    return dict(sorted(counts.items()))


def evaluate(market: dict, forecast: dict, decisions: dict,
             receipts: dict[str, tuple[dict | None, dict | None]]) -> dict:
    expected = groups(forecast, decisions)
    if set(receipts) != set(expected):
        raise ValueError('Fee/quote receipt group scope changed')
    states = Counter()
    group_reports = []
    modeled = 0
    subset_direct = Decimal(0)
    subset_nondirect = Decimal(0)
    for kickoff, count in expected.items():
        fee_receipt, quote_receipt = receipts[kickoff]
        if fee_receipt is not None:
            fee_report = fees.evaluate(market, forecast, decisions, fee_receipt)
            if fee_report['kickoff'] != kickoff or fee_report['frozen_candidates'] != count:
                raise ValueError('Fee receipt belongs to another frozen kickoff')
        if quote_receipt is not None:
            quote_report = prelock.evaluate(market, forecast, decisions, quote_receipt)
            if quote_report['kickoff'] != kickoff or quote_report['frozen_candidates'] != count:
                raise ValueError('Quote receipt belongs to another frozen kickoff')
        if fee_receipt is None or quote_receipt is None:
            missing = ('both_receipts_missing' if fee_receipt is None and quote_receipt is None
                       else 'fee_receipt_missing' if fee_receipt is None
                       else 'quote_receipt_missing')
            states[missing] += count
            group_reports.append({'kickoff': kickoff, 'frozen_candidates': count,
                                  'receipt_state': missing,
                                  'fee_receipt_sha256': fee_receipt['evidence_sha256']
                                      if fee_receipt is not None else None,
                                  'quote_receipt_sha256': quote_receipt['evidence_sha256']
                                      if quote_receipt is not None else None,
                                  'modeled_one_contract_costs': 0})
            continue
        report = fee_score.evaluate(market, forecast, decisions,
                                    fee_receipt, quote_receipt)
        if report['kickoff'] != kickoff or report['frozen_candidates'] != count:
            raise ValueError('Scored receipt group scope changed')
        states.update(report['candidate_states'])
        modeled += report['modeled_one_contract_costs']
        subset_direct += Decimal(report['modeled_subset_direct_total_cost'])
        subset_nondirect += Decimal(report['modeled_subset_nondirect_total_cost'])
        group_reports.append(report)
    if sum(states.values()) != 70 or modeled != states['one_contract_cost_modeled']:
        raise ValueError('Full frozen candidate denominator changed')
    complete = modeled == 70
    return {'protocol': VERSION, 'frozen_candidates': 70,
            'frozen_kickoff_groups': 6, 'groups_with_both_receipts': sum(
                row.get('fee_receipt_sha256') is not None
                and row.get('quote_receipt_sha256') is not None
                for row in group_reports),
            'candidate_states': dict(sorted(states.items())),
            'modeled_one_contract_costs': modeled,
            'modeled_subset_direct_total_cost': str(subset_direct),
            'modeled_subset_nondirect_total_cost': str(subset_nondirect),
            'complete_cost_scenario': complete,
            'full_cohort_direct_total_cost': str(subset_direct) if complete else None,
            'full_cohort_nondirect_total_cost': str(subset_nondirect) if complete else None,
            'conditional_binary_direct_break_even_wins':
                int(subset_direct) + 1 if complete else None,
            'conditional_binary_nondirect_break_even_wins':
                int(subset_nondirect) + 1 if complete else None,
            'group_reports_sha256': digest(group_reports),
            'group_reports': group_reports,
            'single_fill_assumed': True, 'actual_fills_verified': False,
            'venue_results_verified': False, 'roi': None, 'clv': None,
            'edge_established': False, 'qualified_picks': 0}


def _paths(directory: Path, kickoff: str) -> tuple[Path, Path]:
    suffix = clock(kickoff).strftime('%Y%m%dT%H%M')
    return (directory / f'stat-only-prelock-fees-{suffix}.json',
            directory / f'stat-only-prelock-{suffix}.json')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair', 'market', 'forecast', 'quotes', 'decisions'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--receipt-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Cohort report already exists')
    pair, market, forecast, quotes, decisions = (
        _pinned(getattr(args, name), name) for name in
        ('pair', 'market', 'forecast', 'quotes', 'decisions'))
    preflight(pair, market, forecast, quotes, decisions,
              args.source_dir, args.schedule)
    if args.receipt_dir.is_symlink() or not args.receipt_dir.is_dir():
        parser.error('Receipt directory missing or symlinked')
    receipts = {}
    for kickoff in groups(forecast, decisions):
        fee_path, quote_path = _paths(args.receipt_dir, kickoff)
        receipts[kickoff] = tuple(
            fee_score._receipt(path) if path.exists() or path.is_symlink() else None
            for path in (fee_path, quote_path))
    report = evaluate(market, forecast, decisions, receipts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
