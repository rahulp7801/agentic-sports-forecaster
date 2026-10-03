"""Outcome-blind fee scenario for frozen NFL prelock asks.

Joins separate unsigned fee and quote receipts. No provider requests or fills.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path

from sportsbet.arbitrage.kalshi_fees import fee_terms, taker_buy_cost, timestamp
from sportsbet.quant.kalshi_exact_markout import _market_state
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_stat_only_forward_eval import _pinned, preflight
from sportsbet.quant import kalshi_stat_only_prelock as prelock
from sportsbet.quant import kalshi_stat_only_prelock_fees as fees

VERSION = 'kalshi-nfl-stat-only-prelock-fee-scenario-v1'
MAX_RECEIPT_BYTES = 30_000_000


def _observed_quotes(receipt: dict) -> dict[str, tuple[dict | None, dict]]:
    """The prelock verifier has already checked page identity and chronology."""
    observed = {}
    for page in receipt['evidence']['pages']:
        if 'error_type' in page:
            observed.update({ticker: (None, page) for ticker in page['tickers']})
            continue
        by_ticker = {row['ticker']: row for row in page['body']['markets']}
        observed.update({ticker: (by_ticker.get(ticker), page)
                         for ticker in page['tickers']})
    return observed


def evaluate(market: dict, forecast: dict, decisions: dict,
             fee_receipt: dict, quote_receipt: dict,
             *, include_cost_rows: bool = False) -> dict:
    fee_report = fees.evaluate(market, forecast, decisions, fee_receipt)
    quote_report = prelock.evaluate(market, forecast, decisions, quote_receipt)
    if (fee_report['kickoff'] != quote_report['kickoff']
            or fee_report['frozen_candidates'] != quote_report['frozen_candidates']):
        raise ValueError('Fee and quote kickoff scopes differ')
    kickoff = clock(fee_report['kickoff'])
    selected, events = fees.identities(market, forecast, decisions, kickoff)
    originals = market['evidence']['sources']['kalshi']['prop_inventory']['quotes']
    by_ticker = {row['ticker']: row for row in originals}
    observed = _observed_quotes(quote_receipt)
    if not set(row['ticker'] for row in selected) <= set(observed):
        raise ValueError('Prelock quote denominator changed')
    contexts = fee_receipt['evidence']['sources']
    states, quote_states = Counter(), Counter()
    costed = []
    for candidate in selected:
        ticker = candidate['ticker']
        original = by_ticker[ticker]
        current, page = observed[ticker]
        if current is None:
            state = 'batch_unavailable' if 'error_type' in page else 'missing_exact_contract'
            quote_states[state] += 1
            states[state] += 1
            continue
        quote_state, ask = _market_state(current, original, candidate['side'])
        quote_states[quote_state] += 1
        if quote_state != 'prelock_exact_ask':
            states[quote_state] += 1
            continue
        event = original['event_ticker']
        if event not in events or contexts[event]['status'] != 'observed':
            states['fee_unavailable'] += 1
            continue
        context = contexts[event]['context']
        quote_started, quote_received = (
            clock(page[key]) for key in ('request_started_at', 'received_at'))
        fee_received = clock(context['received_at'])
        if not fee_received <= quote_started <= quote_received:
            states['fee_after_quote'] += 1
            continue
        waiver = current.get('fee_waiver_expiration_time')
        if waiver is not None:
            try:
                unresolved = (not isinstance(waiver, str)
                              or timestamp(waiver) > quote_received)
            except ValueError:
                unresolved = True
            if unresolved:
                states['fee_waiver_unresolved'] += 1
                continue
        try:
            _, multiplier = fee_terms(context, event, quote_received)
        except (KeyError, TypeError, ValueError, ArithmeticError):
            states['fee_changed_or_stale'] += 1
            continue
        direct = Decimal(taker_buy_cost(ask, Decimal(1), multiplier,
                                        Decimal('.0001'))['total_cost'])
        nondirect = Decimal(taker_buy_cost(ask, Decimal(1), multiplier,
                                           Decimal('.01'))['total_cost'])
        states['one_contract_cost_modeled'] += 1
        costed.append({'ticker': ticker, 'milestone_id': candidate['milestone_id'],
                       'ask': str(ask), 'direct_total': str(direct),
                       'nondirect_total': str(nondirect)})
    if (dict(sorted(quote_states.items())) != quote_report['candidate_state_counts']
            or sum(states.values()) != len(selected)
            or len(costed) != states['one_contract_cost_modeled']):
        raise ValueError('Fee/quote scoring denominator changed')
    direct_total = sum((Decimal(row['direct_total']) for row in costed), Decimal(0))
    nondirect_total = sum((Decimal(row['nondirect_total']) for row in costed), Decimal(0))
    complete = len(costed) == len(selected)
    report = {'protocol': VERSION, 'kickoff': fee_report['kickoff'],
            'frozen_candidates': len(selected),
            'frozen_games': len({row['milestone_id'] for row in selected}),
            'fee_receipt_sha256': fee_receipt['evidence_sha256'],
            'quote_receipt_sha256': quote_receipt['evidence_sha256'],
            'candidate_states': dict(sorted(states.items())),
            'modeled_cost_rows_sha256': digest(costed),
            'modeled_one_contract_costs': len(costed),
            'modeled_subset_direct_total_cost': str(direct_total),
            'modeled_subset_nondirect_total_cost': str(nondirect_total),
            'complete_cost_scenario': complete,
            'full_group_direct_total_cost': str(direct_total) if complete else None,
            'full_group_nondirect_total_cost': str(nondirect_total) if complete else None,
            'conditional_binary_direct_break_even_wins':
                (int(direct_total) + 1) if complete else None,
            'conditional_binary_nondirect_break_even_wins':
                (int(nondirect_total) + 1) if complete else None,
            'single_fill_assumed': True, 'actual_fills_verified': False,
            'venue_results_verified': False, 'roi': None, 'clv': None,
            'edge_established': False, 'qualified_picks': 0}
    if include_cost_rows:
        report['modeled_cost_rows'] = costed
    return report


def _receipt(path: Path) -> dict:
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= MAX_RECEIPT_BYTES):
        raise ValueError('Receipt missing or unbounded')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('Receipt must be an object')
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair', 'market', 'forecast', 'quotes', 'decisions'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--fee-receipt', type=Path, required=True)
    parser.add_argument('--quote-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Scenario output already exists')
    pair, market, forecast, quotes, decisions = (
        _pinned(getattr(args, name), name) for name in
        ('pair', 'market', 'forecast', 'quotes', 'decisions'))
    preflight(pair, market, forecast, quotes, decisions,
              args.source_dir, args.schedule)
    report = evaluate(market, forecast, decisions,
                      _receipt(args.fee_receipt), _receipt(args.quote_receipt))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
