"""Outcome-blind later-ask fee scenario for the original fixed 11 NFL picks.

The exact high-probability subset was frozen before the first selected kickoff.
This offline diagnostic cannot change picks, prices, or probabilities and
cannot prove fills, wins, ROI, or an executable edge.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path

from sportsbet.quant import kalshi_stat_only_high_probability_eval as high
from sportsbet.quant import kalshi_stat_only_prelock_fee_score as fees
from sportsbet.quant import kalshi_stat_only_prelock_fee_cohort as cohort
from sportsbet.quant import kalshi_stat_only_prior20_eval as prior
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_stat_only_forward_eval import _pinned

VERSION = 'kalshi-nfl-stat-only-fixed-high-fee-scenario-v1'
HIGH_TICKERS_SHA256 = 'b3383ce6c65abac15e17b69a8063393c75218e07ce38d6c1cd898fcac8c8c42e'


def evaluate(market: dict, forecast: dict, decisions: dict, control: dict,
             high_report: dict, receipts: dict[str, tuple[dict, dict]]) -> dict:
    candidates = decisions['candidates']
    selected = {row['ticker']: row for row in candidates
                if Decimal(str(row['model_win_probability'])) >= high.THRESHOLD}
    if (len(candidates) != 70 or len(selected) != 11
            or len({row['milestone_id'] for row in selected.values()}) != 8
            or digest(sorted(selected)) != HIGH_TICKERS_SHA256
            or high_report['selected_tickers_sha256'] != HIGH_TICKERS_SHA256
            or high_report['paper_candidates'] != 11
            or high_report['paper_games'] != 8):
        raise ValueError('Original fixed high-probability subgroup changed')
    starts = {row['ticker']: clock(row['scheduled_game_start_time']).isoformat()
              for row in forecast['forecasts']}
    if len(starts) != len(forecast['forecasts']) or not set(selected) <= set(starts):
        raise ValueError('Original forecast kickoff identity changed')
    required = {starts[ticker] for ticker in selected}
    if set(receipts) != required:
        raise ValueError('High-probability kickoff receipt scope changed')
    prior_rows = {row['ticker']: row for row in control['forecast_rows']}
    if len(prior_rows) != len(control['forecast_rows']) or not set(selected) <= set(prior_rows):
        raise ValueError('Strict prior control identity changed')
    cost_rows = {}
    receipt_hashes = {}
    group_states = Counter()
    for kickoff, (fee_receipt, quote_receipt) in sorted(receipts.items()):
        report = fees.evaluate(market, forecast, decisions, fee_receipt,
                               quote_receipt, include_cost_rows=True)
        if report['kickoff'] != kickoff:
            raise ValueError('Fee and quote group kickoff changed')
        receipt_hashes[kickoff] = dict(fee=report['fee_receipt_sha256'],
                                      quotes=report['quote_receipt_sha256'])
        group_states.update(report['candidate_states'])
        for row in report['modeled_cost_rows']:
            ticker = row['ticker']
            if ticker not in selected:
                continue
            if ticker in cost_rows or starts[ticker] != kickoff:
                raise ValueError('Duplicate or cross-group high-probability cost')
            if row['milestone_id'] != selected[ticker]['milestone_id']:
                raise ValueError('High-probability cost identity changed')
            cost_rows[ticker] = row
    complete = set(cost_rows) == set(selected)
    rows = []
    for ticker, cost in sorted(cost_rows.items()):
        candidate = selected[ticker]
        side = candidate['side']
        over = Decimal(str(prior_rows[ticker]['prior20_over_probability']))
        model = Decimal(str(candidate['model_win_probability']))
        strict = over if side == 'yes' else 1 - over
        ask = Decimal(cost['ask'])
        direct = Decimal(cost['direct_total'])
        nondirect = Decimal(cost['nondirect_total'])
        if (side not in ('yes', 'no') or not 0 < model < 1
                or not 0 < strict < 1 or not 0 < ask <= direct <= nondirect):
            raise ValueError('Invalid frozen probability or fee-aware cost')
        rows.append((model, strict, direct, nondirect))
    report = dict(protocol=VERSION, primary_paper_candidates=70,
                  fixed_high_probability_candidates=11, fixed_high_probability_games=8,
                  fixed_tickers_sha256=HIGH_TICKERS_SHA256,
                  observed_high_probability_costs=len(rows),
                  missing_high_probability_costs=11-len(rows),
                  high_probability_cost_complete=complete,
                  full_group_candidate_states=dict(sorted(group_states.items())),
                  prelock_receipt_sha256=receipt_hashes,
                  modeled_cost_rows_sha256=digest([cost_rows[t] for t in sorted(cost_rows)]),
                  actual_fills_verified=False, outcomes_used=False,
                  edge_established=False, qualified_picks=0, roi=None, clv=None)
    for label, index in (('direct', 2), ('nondirect', 3)):
        total = sum((row[index] for row in rows), Decimal(0))
        report[f'{label}_observed_cost_total'] = str(total)
        report[f'{label}_full_cost_total'] = str(total) if complete else None
        report[f'{label}_full_binary_break_even_wins'] = int(total)+1 if complete else None
        for name, probability_index in (('model', 0), ('strict_prior20', 1)):
            projected = sum((row[probability_index] for row in rows), Decimal(0))
            report[f'{label}_{name}_observed_projected_wins'] = str(projected)
            report[f'{label}_{name}_full_projected_net_units'] = (
                str(projected-total) if complete else None)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair', 'market', 'forecast', 'quotes', 'decisions'):
        parser.add_argument('--'+name, type=Path, required=True)
    for name in ('source-dir', 'schedule', 'control', 'receipt-dir', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Exclusive scenario output already exists')
    pair, market, forecast, quotes, decisions = (
        _pinned(getattr(args, name), name) for name in
        ('pair', 'market', 'forecast', 'quotes', 'decisions'))
    high_report = high.evaluate(pair, market, forecast, quotes, decisions,
                                args.source_dir, args.schedule)
    control = prior.pinned_control(args.control, forecast, decisions)
    if args.receipt_dir.is_symlink() or not args.receipt_dir.is_dir():
        parser.error('Private receipt directory unavailable')
    starts = {row['ticker']: clock(row['scheduled_game_start_time']).isoformat()
              for row in forecast['forecasts']}
    kickoffs = {starts[row['ticker']] for row in decisions['candidates']
                if Decimal(str(row['model_win_probability'])) >= high.THRESHOLD}
    receipts = {}
    for kickoff in kickoffs:
        fee_path, quote_path = cohort._paths(args.receipt_dir, kickoff)
        receipts[kickoff] = (fees._receipt(fee_path), fees._receipt(quote_path))
    report = evaluate(market, forecast, decisions, control, high_report, receipts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
