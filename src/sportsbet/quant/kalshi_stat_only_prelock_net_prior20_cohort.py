"""Offline fee-aware model/strict-prior comparison on all fixed paper decisions.

Uncaptured or invalid kickoff groups stay in the original 70-decision
denominator. Only a fully covered cohort can have a full-cohort cost scenario.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path

from sportsbet.quant import kalshi_stat_only_prelock_fee_cohort as fee_cohort
from sportsbet.quant import kalshi_stat_only_prelock_fee_score as fee_score
from sportsbet.quant import kalshi_stat_only_prelock_net_prior20 as net_prior20
from sportsbet.quant.kalshi_market_cohort import digest
from sportsbet.quant.kalshi_stat_only_forward_eval import _pinned, preflight
from sportsbet.quant.kalshi_stat_only_prior20_eval import pinned_control, CONTROL_SHA256

VERSION = 'kalshi-nfl-stat-only-prelock-net-prior20-cohort-v1'
MARGIN_KEYS = tuple(
    f'{mode}_{name}_net_margin_at_least_5pp'
    for mode in ('direct', 'nondirect')
    for name in ('model', 'strict_prior20'))
MEAN_KEYS = tuple(
    f'{mode}_{name}_mean_net_margin'
    for mode in ('direct', 'nondirect')
    for name in ('model', 'strict_prior20'))


def evaluate(market: dict, forecast: dict, decisions: dict, control: dict,
             receipts: dict[str, tuple[dict | None, dict | None]]) -> dict:
    expected = fee_cohort.groups(forecast, decisions)
    audit = fee_cohort.evaluate(market, forecast, decisions, receipts)
    group_reports = []
    counts = {key: 0 for key in MARGIN_KEYS}
    weighted = {key: Decimal(0) for key in MEAN_KEYS}
    scored = 0
    for kickoff, size in expected.items():
        fee_receipt, quote_receipt = receipts[kickoff]
        if fee_receipt is None or quote_receipt is None:
            group_reports.append({'kickoff': kickoff, 'frozen_candidates': size,
                                  'modeled_cost_subset': 0,
                                  'receipt_state': 'both_receipts_missing'
                                      if fee_receipt is None and quote_receipt is None
                                      else 'fee_receipt_missing' if fee_receipt is None
                                      else 'quote_receipt_missing'})
            continue
        report = net_prior20.evaluate(market, forecast, decisions, control,
                                      fee_receipt, quote_receipt)
        if report['kickoff'] != kickoff or report['frozen_candidates'] != size:
            raise ValueError('Net-control group differs from fixed kickoff scope')
        scored += report['modeled_cost_subset']
        for key in MARGIN_KEYS:
            counts[key] += report[key]
        for key in MEAN_KEYS:
            if report[key] is not None:
                weighted[key] += Decimal(report[key]) * report['modeled_cost_subset']
        group_reports.append(report)
    if (scored != audit['modeled_one_contract_costs']
            or len(group_reports) != 6 or sum(row['frozen_candidates']
                for row in group_reports) != 70):
        raise ValueError('Net and fee cohort denominators differ')
    complete = scored == 70
    result = {'protocol': VERSION, 'frozen_candidates': 70,
              'frozen_kickoff_groups': 6,
              'groups_with_both_receipts': audit['groups_with_both_receipts'],
              'modeled_cost_subset': scored, 'missing_modeled_costs': 70 - scored,
              'candidate_states': audit['candidate_states'],
              'fee_cohort_group_reports_sha256': audit['group_reports_sha256'],
              'strict_prior20_control_sha256': CONTROL_SHA256,
              'original_decisions_sha256': digest(decisions),
              'group_reports_sha256': digest(group_reports),
              'group_reports': group_reports,
              'complete_cost_scenario': complete}
    for key in MARGIN_KEYS:
        result[f'modeled_subset_{key}'] = counts[key]
        result[f'full_cohort_{key}'] = counts[key] if complete else None
    for key in MEAN_KEYS:
        result[f'modeled_subset_{key}'] = str(weighted[key] / scored) if scored else None
        result[f'full_cohort_{key}'] = str(weighted[key] / scored) if complete else None
    result.update(single_contract_assumed=True, actual_fills_verified=False,
                  outcomes_used=False, roi=None, clv=None,
                  edge_established=False, qualified_picks=0)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair', 'market', 'forecast', 'quotes', 'decisions'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--receipt-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Exclusive offline cohort output already exists')
    pair, market, forecast, quotes, decisions = (
        _pinned(getattr(args, name), name) for name in
        ('pair', 'market', 'forecast', 'quotes', 'decisions'))
    preflight(pair, market, forecast, quotes, decisions,
              args.source_dir, args.schedule)
    control = pinned_control(args.control, forecast, decisions)
    if args.receipt_dir.is_symlink() or not args.receipt_dir.is_dir():
        parser.error('Receipt directory missing or symlinked')
    receipts = {}
    for kickoff in fee_cohort.groups(forecast, decisions):
        fee_path, quote_path = fee_cohort._paths(args.receipt_dir, kickoff)
        receipts[kickoff] = tuple(
            fee_score._receipt(path) if path.exists() or path.is_symlink() else None
            for path in (fee_path, quote_path))
    report = evaluate(market, forecast, decisions, control, receipts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps({key: value for key, value in report.items()
                      if key != 'group_reports'}, sort_keys=True))


if __name__ == '__main__':
    main()
