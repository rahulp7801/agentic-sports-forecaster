"""Frozen one-contract Kalshi fee scenario, scored only on exact venue results.

This is an unfilled research counterfactual. It never places an order, infers
fills, publishes a pick, or establishes a betting edge.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from sportsbet.arbitrage.kalshi_fees import fee_terms, taker_buy_cost, timestamp
from sportsbet.quant import kalshi_ask_policy, kalshi_prior20_ask_policy
from sportsbet.quant.kalshi_market_cohort import digest
from sportsbet.quant.kalshi_market_settlement import venue_results, verify_cohort
from sportsbet.quant.kalshi_pair_capture import MAX_PAIR_BYTES, unpack
from sportsbet.quant.kalshi_role_shadow_eval import _interval

VERSION = 'kalshi-nfl-fee-inclusive-unit-shadow-v1'
MAX_ARCHIVE_BYTES = 30_000_000
POLICIES = {'role': ('ask_policy', kalshi_ask_policy),
            'prior20': ('prior20_ask_policy', kalshi_prior20_ask_policy)}
SOURCE_FIELDS = ('ticker', 'milestone_id', 'player_target_id', 'team_target_id',
                 'prop_type', 'line', 'received_at', 'scheduled_game_start_time',
                 'market_sha256', 'rules_sha256', 'source_page_sha256',
                 'yes_ask', 'no_ask')


def preoutcome(pair: dict, market_archive: dict, *, policy: str = 'role') -> tuple[dict, list[dict]]:
    """Reprice every frozen candidate at its own captured event fee terms."""
    if policy not in POLICIES:
        raise ValueError('Unknown frozen ask policy')
    receipt_key, module = POLICIES[policy]
    cohort, _ = unpack(pair)
    verify_cohort(market_archive, cohort)
    frozen = module.freeze(pair)
    if pair.get(receipt_key) != frozen:
        raise ValueError('Frozen ask policy receipt changed')
    inventory = market_archive['evidence']['sources']['kalshi']['prop_inventory']
    quotes = inventory['quotes']
    by_quote = {row['ticker']: row for row in quotes}
    by_offer = {row['ticker']: row for row in cohort['selections']}
    if len(by_quote) != len(quotes) or len(by_offer) != len(cohort['selections']):
        raise ValueError('Duplicate source quote or selected contract')
    contexts = inventory['fee_contexts']
    rows = []
    for candidate in frozen['candidates']:
        ticker, side = candidate['ticker'], candidate['side']
        if side not in ('yes', 'no') or ticker not in by_quote or ticker not in by_offer:
            raise ValueError('Candidate source identity unavailable')
        quote, offer = by_quote[ticker], by_offer[ticker]
        if any(quote[field] != offer[field] for field in SOURCE_FIELDS):
            raise ValueError('Frozen candidate differs from exact source quote')
        ask = offer[side + '_ask']
        if (candidate['displayed_ask'] != ask['cost']
                or candidate['displayed_size'] != ask['displayed_size']
                or Decimal(candidate['displayed_size']) < 1):
            raise ValueError('Frozen candidate lacks one displayed contract')
        as_of = timestamp(offer['received_at'])
        waiver = quote.get('fee_waiver_expiration_time')
        if waiver is not None and timestamp(waiver) > as_of:
            raise ValueError('Active fee waiver requires separate accounting')
        event = quote['event_ticker']
        context = contexts[event]
        if (not isinstance(event, str) or not ticker.startswith(event + '-')
                or context['event_ticker'] != event
                or context['series']['ticker'] != quote['series_ticker']):
            raise ValueError('Fee context event or series identity changed')
        _, multiplier = fee_terms(context, event, as_of)
        price = Decimal(candidate['displayed_ask'])
        direct = taker_buy_cost(price, Decimal(1), multiplier, Decimal('.0001'))
        nondirect = taker_buy_cost(price, Decimal(1), multiplier, Decimal('.01'))
        rows.append(dict(ticker=ticker, milestone_id=candidate['milestone_id'],
                         player_target_id=candidate['player_target_id'], side=side,
                         displayed_ask=candidate['displayed_ask'],
                         direct_total_cost=direct['total_cost'],
                         direct_exchange_fee=direct['exchange_fee'],
                         nondirect_total_cost=nondirect['total_cost'],
                         fee_context_event=event))
    if len(rows) != frozen['candidates_count']:
        raise AssertionError('Fee scenario candidate denominator changed')
    direct_total = sum(Decimal(row['direct_total_cost']) for row in rows)
    nondirect_total = sum(Decimal(row['nondirect_total_cost']) for row in rows)
    report = dict(protocol=VERSION, policy=policy,
                  market_selection_sha256=cohort['selection_sha256'],
                  model_forecasts_sha256=frozen['model_forecasts_sha256'],
                  candidates_sha256=frozen['candidates_sha256'],
                  candidate_cost_rows_sha256=digest(rows),
                  candidates=len(rows), candidate_games=frozen['candidate_games'],
                  modeled_one_contract_costs=len(rows),
                  all_candidates_direct_cost=str(direct_total),
                  all_candidates_nondirect_cost=str(nondirect_total),
                  conditional_binary_direct_break_even_wins=(int(direct_total) + 1
                      if rows else None),
                  conditional_binary_nondirect_break_even_wins=(int(nondirect_total) + 1
                      if rows else None),
                  modeled_exchange_fees=True, actual_fills_verified=False,
                  model_source_replayed=False, edge_established=False,
                  qualified_picks=0, roi=None, clv=None, execution_ready=False)
    return report, rows


def evaluate(pair: dict, market_archive: dict, source_dir: Path, settlements: dict,
             *, policy: str = 'role', now: datetime | None = None) -> dict:
    """Keep unavailable/nonbinary contracts in the full frozen denominator."""
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError('Settlement audit requires an aware clock')
    pre, costs = preoutcome(pair, market_archive, policy=policy)
    _, module = POLICIES[policy]
    gross = module.audit(pair, market_archive, source_dir, settlements, now=now)
    if (gross['candidates_sha256'] != pre['candidates_sha256']
            or gross['candidates'] != pre['candidates']
            or gross['market_selection_sha256'] != pre['market_selection_sha256']):
        raise ValueError('Gross policy audit differs from frozen fee cohort')
    cohort, _ = unpack(pair)
    _, states = venue_results(market_archive, cohort, settlements, now=now)
    counts = Counter()
    verified_games = set()
    direct_paid = nondirect_paid = Decimal(0)
    by_game: dict[str, list[Decimal]] = defaultdict(list)
    wins = 0
    for row in costs:
        state, result = states[row['ticker']]
        counts[state] += 1
        if state != 'venue_verified':
            continue
        verified_games.add(row['milestone_id'])
        direct_paid += Decimal(row['direct_total_cost'])
        nondirect_paid += Decimal(row['nondirect_total_cost'])
        win = int(result == row['side'])
        wins += win
        by_game[row['milestone_id']].append(
            Decimal(win) - Decimal(row['direct_total_cost']))
    verified = counts['venue_verified']
    if (sum(counts.values()) != pre['candidates']
            or counts != Counter(gross['candidate_result_counts'])
            or verified != gross['verified_candidates']):
        raise ValueError('Fee and gross settlement denominators disagree')
    complete = pre['candidates'] > 0 and verified == pre['candidates']
    game_means = {game: sum(values) / len(values)
                  for game, values in by_game.items()}
    equal_game = (sum(game_means.values()) / len(game_means)
                  if game_means else None)
    game_interval = _interval({game: (float(value), 1.0)
                               for game, value in game_means.items()})
    return pre | dict(settlement_evidence_sha256=settlements['evidence_sha256'],
                      candidate_result_counts=dict(sorted(counts.items())),
                      verified_binary_candidates=verified,
                      verified_candidate_games=len(verified_games),
                      verified_subset_wins=wins,
                      verified_subset_equal_game_direct_unit_profit_per_candidate=(
                          str(equal_game) if equal_game is not None else None),
                      verified_subset_equal_game_direct_game_cluster_95=game_interval,
                      verified_subset_hypothetical_direct_cost=str(direct_paid),
                      verified_subset_hypothetical_nondirect_cost=str(nondirect_paid),
                      verified_subset_hypothetical_direct_unit_profit=(
                          str(Decimal(wins)-direct_paid) if verified else None),
                      verified_subset_hypothetical_nondirect_unit_profit=(
                          str(Decimal(wins)-nondirect_paid) if verified else None),
                      full_cohort_hypothetical_direct_unit_profit=(
                          str(Decimal(wins)-direct_paid) if complete else None),
                      complete_binary_results=complete, model_source_replayed=True)


def _load(path: Path, limit: int) -> dict:
    if path.is_symlink() or not 0 < path.stat().st_size <= limit:
        raise ValueError('Input is absent, linked, empty, or exceeds size bound')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('Research input must be an object')
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', type=Path, required=True)
    parser.add_argument('--market-archive', type=Path, required=True)
    parser.add_argument('--policy', choices=sorted(POLICIES), default='role')
    parser.add_argument('--source-dir', type=Path)
    parser.add_argument('--settlements', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Output already exists')
    pair = _load(args.pair, MAX_PAIR_BYTES)
    archive = _load(args.market_archive, MAX_ARCHIVE_BYTES)
    if args.settlements:
        if args.source_dir is None:
            parser.error('--source-dir is required with --settlements')
        report = evaluate(pair, archive, args.source_dir,
                          _load(args.settlements, MAX_ARCHIVE_BYTES), policy=args.policy)
    else:
        report, _ = preoutcome(pair, archive, policy=args.policy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
