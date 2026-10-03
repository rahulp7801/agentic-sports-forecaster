"""Outcome-blind, fee-aware model versus strict last-20 on fixed paper picks.

Only the modeled-cost subset of a frozen kickoff group is compared. Displayed
asks and one-contract taker fees are a scenario, never verified fills or edge.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from sportsbet.quant import kalshi_stat_only_prelock as prelock
from sportsbet.quant import kalshi_stat_only_prelock_fee_score as fee_score
from sportsbet.quant import kalshi_stat_only_prelock_prior20 as prior20
from sportsbet.quant.kalshi_market_cohort import digest
from sportsbet.quant.kalshi_stat_only_forward_eval import _pinned, preflight
from sportsbet.quant.kalshi_stat_only_prior20_eval import pinned_control, CONTROL_SHA256

VERSION = 'kalshi-nfl-stat-only-prelock-net-prior20-v1'
MIN_MARGIN = Decimal('.05')


def summarize(selected: list[dict], control: dict, fee_report: dict) -> dict:
    by_prior = {row['ticker']: row for row in control['forecast_rows']}
    by_candidate = {row['ticker']: row for row in selected}
    rows = fee_report['modeled_cost_rows']
    if (len(by_candidate) != len(selected)
            or len(by_prior) != len(control['forecast_rows'])
            or len(rows) != fee_report['modeled_one_contract_costs']
            or digest(rows) != fee_report['modeled_cost_rows_sha256']
            or len({row['ticker'] for row in rows}) != len(rows)
            or not {row['ticker'] for row in rows} <= set(by_candidate)):
        raise ValueError('Fixed candidate or modeled-cost row identity changed')
    modeled = []
    for row in rows:
        candidate = by_candidate[row['ticker']]
        if (row['milestone_id'] != candidate['milestone_id']
                or candidate['ticker'] not in by_prior):
            raise ValueError('Cost row differs from frozen forecast identity')
        model = Decimal(str(candidate['model_win_probability']))
        over = Decimal(str(by_prior[row['ticker']]['prior20_over_probability']))
        side = candidate['side']
        strict = over if side == 'yes' else 1 - over
        ask = Decimal(row['ask'])
        direct = Decimal(row['direct_total'])
        nondirect = Decimal(row['nondirect_total'])
        if (side not in ('yes', 'no') or not 0 < model < 1
                or not 0 < strict < 1 or not 0 < ask < 1
                or not ask <= direct <= nondirect):
            raise ValueError('Invalid fixed probability or modeled taker cost')
        modeled.append((model, strict, direct, nondirect))
    n = len(modeled)
    result = {'protocol': VERSION,
              'frozen_candidates': len(selected),
              'frozen_games': len({row['milestone_id'] for row in selected}),
              'modeled_cost_subset': n,
              'missing_modeled_costs': len(selected) - n,
              'candidate_states': fee_report['candidate_states'],
              'modeled_cost_rows_sha256': fee_report['modeled_cost_rows_sha256'],
              'fee_receipt_sha256': fee_report['fee_receipt_sha256'],
              'quote_receipt_sha256': fee_report['quote_receipt_sha256']}
    for label, index in (('direct', 2), ('nondirect', 3)):
        result[f'{label}_mean_one_contract_cost'] = (
            str(sum((row[index] for row in modeled), Decimal(0)) / n) if n else None)
        for name, probability_index in (('model', 0), ('strict_prior20', 1)):
            margins = [row[probability_index] - row[index] for row in modeled]
            result[f'{label}_{name}_mean_net_margin'] = (
                str(sum(margins, Decimal(0)) / n) if n else None)
            result[f'{label}_{name}_net_margin_at_least_5pp'] = sum(
                margin >= MIN_MARGIN for margin in margins)
    result.update(single_contract_assumed=True, actual_fills_verified=False,
                  outcomes_used=False, roi=None, edge_established=False,
                  qualified_picks=0)
    return result


def evaluate(market: dict, forecast: dict, decisions: dict, control: dict,
             fee_receipt: dict, quote_receipt: dict) -> dict:
    prior_report = prior20.evaluate(market, forecast, decisions, control, quote_receipt)
    fee_report = fee_score.evaluate(market, forecast, decisions,
                                    fee_receipt, quote_receipt,
                                    include_cost_rows=True)
    if (prior_report['kickoff'] != fee_report['kickoff']
            or prior_report['frozen_candidates'] != fee_report['frozen_candidates']
            or prior_report['later_receipt_sha256'] != fee_report['quote_receipt_sha256']):
        raise ValueError('Strict control, fee and quote groups differ')
    selected, _ = prelock.scope(forecast, decisions, prelock.clock(prior_report['kickoff']))
    if digest(selected) != prior_report['candidate_rows_sha256']:
        raise ValueError('Frozen candidate rows changed')
    report = summarize(selected, control, fee_report)
    report.update(kickoff=prior_report['kickoff'],
                  original_decisions_sha256=digest(decisions),
                  strict_prior20_control_sha256=CONTROL_SHA256,
                  candidate_rows_sha256=digest(selected))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair', 'market', 'forecast', 'quotes', 'decisions'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--fee-receipt', type=Path, required=True)
    parser.add_argument('--quote-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Exclusive offline diagnostic output already exists')
    pair, market, forecast, quotes, decisions = (
        _pinned(getattr(args, name), name) for name in
        ('pair', 'market', 'forecast', 'quotes', 'decisions'))
    preflight(pair, market, forecast, quotes, decisions,
              args.source_dir, args.schedule)
    control = pinned_control(args.control, forecast, decisions)
    report = evaluate(market, forecast, decisions, control,
                      fee_score._receipt(args.fee_receipt),
                      fee_score._receipt(args.quote_receipt))
    report['computed_at'] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
