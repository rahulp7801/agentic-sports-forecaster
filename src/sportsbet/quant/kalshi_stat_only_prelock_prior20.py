"""Outcome-blind later-ask comparison on the fixed October 4 paper decisions.

The model, strict last-20 control, exact contracts and candidate membership
are already frozen. This offline report never reads results or changes picks.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from sportsbet.quant.kalshi_market_cohort import digest
from sportsbet.quant.kalshi_stat_only_forward_eval import _pinned, preflight
from sportsbet.quant.kalshi_stat_only_prior20_eval import pinned_control, CONTROL_SHA256
from sportsbet.quant import kalshi_stat_only_prelock as prelock

VERSION = 'kalshi-nfl-stat-only-prelock-prior20-v1'
MIN_MARGIN = Decimal('.05')


def summarize(selected: list[dict], control: dict, observed: dict) -> dict:
    by_prior = {row['ticker']: row for row in control['forecast_rows']}
    counts = Counter()
    model_probs, prior_probs, asks = [], [], []
    model_margins, prior_margins = [], []
    games = set()
    for candidate in selected:
        ticker = candidate['ticker']
        games.add(candidate['milestone_id'])
        state, ask = observed[ticker]
        counts[state] += 1
        if state != 'prelock_exact_ask':
            continue
        model = Decimal(str(candidate['model_win_probability']))
        over = Decimal(str(by_prior[ticker]['prior20_over_probability']))
        prior = over if candidate['side'] == 'yes' else 1-over
        if (candidate['side'] not in ('yes', 'no') or not 0 < model < 1
                or not 0 < prior < 1 or ask is None or not 0 < ask < 1):
            raise ValueError('Fixed side probability or exact ask invalid')
        model_probs.append(model)
        prior_probs.append(prior)
        asks.append(ask)
        model_margins.append(model-ask)
        prior_margins.append(prior-ask)
    n = len(asks)
    return dict(protocol=VERSION, frozen_candidates=len(selected),
        frozen_games=len(games), quote_states=dict(sorted(counts.items())),
        matched_later_asks=n,
        mean_model_side_probability=str(sum(model_probs)/n) if n else None,
        mean_strict_prior20_side_probability=str(sum(prior_probs)/n) if n else None,
        mean_later_displayed_ask=str(sum(asks)/n) if n else None,
        model_gross_margin_at_least_5pp=sum(m>=MIN_MARGIN for m in model_margins),
        strict_prior20_gross_margin_at_least_5pp=sum(m>=MIN_MARGIN for m in prior_margins),
        mean_model_minus_later_ask=str(sum(model_margins)/n) if n else None,
        mean_strict_prior20_minus_later_ask=str(sum(prior_margins)/n) if n else None,
        outcomes_used=False, fills_verified=False, fees_included=False,
        edge_established=False, qualified_picks=0)


def evaluate(market: dict, forecast: dict, decisions: dict,
             control: dict, receipt: dict) -> dict:
    checked = prelock.evaluate(market, forecast, decisions, receipt)
    kickoff = receipt['evidence']['kickoff']
    selected, tickers = prelock.scope(forecast, decisions, prelock.clock(kickoff))
    originals = {row['ticker']: row for row in
        market['evidence']['sources']['kalshi']['prop_inventory']['quotes']}
    returned = {}
    missing = {}
    for page in receipt['evidence']['pages']:
        if 'error_type' in page:
            missing.update({ticker: 'batch_unavailable' for ticker in page['tickers']})
        else:
            batch = {row['ticker']: row for row in page['body']['markets']}
            returned.update(batch)
            missing.update({ticker: 'missing_exact_contract' for ticker in page['tickers']
                            if ticker not in batch})
    observed = {}
    for candidate in selected:
        ticker = candidate['ticker']
        if ticker not in returned:
            observed[ticker] = (missing[ticker], None)
        else:
            observed[ticker] = prelock._market_state(
                returned[ticker], originals[ticker], candidate['side'])
    report = summarize(selected, control, observed)
    if (set(observed) != set(tickers)
            or report['quote_states'] != checked['candidate_state_counts']
            or report['matched_later_asks'] != checked['matched_candidates']):
        raise ValueError('Later-ask pair scope differs from fixed prelock audit')
    report.update(kickoff=kickoff,
                  original_decisions_sha256=digest(decisions),
                  strict_prior20_control_sha256=CONTROL_SHA256,
                  later_receipt_sha256=receipt['evidence_sha256'],
                  candidate_rows_sha256=digest(selected))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair','market','forecast','quotes','decisions'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--prelock', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Exclusive offline diagnostic output already exists')
    pair, market, forecast, quotes, decisions = (
        _pinned(getattr(args, name), name) for name in
        ('pair','market','forecast','quotes','decisions'))
    preflight(pair, market, forecast, quotes, decisions,
              args.source_dir, args.schedule)
    control = pinned_control(args.control, forecast, decisions)
    if (args.prelock.is_symlink() or not args.prelock.is_file()
            or not 0 < args.prelock.stat().st_size <= 2_000_000):
        parser.error('Later exact-quote receipt missing or unbounded')
    receipt = json.loads(args.prelock.read_text(encoding='utf-8'))
    report = evaluate(market, forecast, decisions, control, receipt)
    report['computed_at'] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
