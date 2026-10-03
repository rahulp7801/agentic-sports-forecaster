"""Bounded public exact-ticker ask check after a frozen NFL research decision.

The capture uses unsigned GET requests and retains raw provider responses. An
ask change is neither a fill nor a closing line, return, or betting edge.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

from sportsbet.ingestion.kalshi import KalshiReader, READ_RETRY_DELAYS
from sportsbet.quant.kalshi_fee_score import MAX_ARCHIVE_BYTES, POLICIES, _load, preoutcome
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_pair_capture import MAX_PAIR_BYTES
from sportsbet.quant.kalshi_role_shadow_eval import _interval


VERSION = 'kalshi-nfl-exact-ticker-markout-v1'
BATCH_SIZE = 20
MAX_TICKERS = 200
MAX_RECEIPT_BYTES = 10_000_000


def _frozen(pair: dict, original: dict) -> tuple[list[str], datetime]:
    candidates = []
    for policy, (key, _) in POLICIES.items():
        pre, _ = preoutcome(pair, original, policy=policy)
        receipt = pair[key]
        if pre['candidates'] != len(receipt['candidates']):
            raise ValueError('Frozen candidate count changed')
        candidates.extend(receipt['candidates'])
    tickers = sorted({row['ticker'] for row in candidates})
    if not 0 < len(tickers) <= MAX_TICKERS:
        raise ValueError('Exact ticker cohort is empty or unbounded')
    quotes = {row['ticker']: row for row in original['evidence']['sources']['kalshi']['prop_inventory']['quotes']}
    first_lock = min(clock(quotes[ticker]['scheduled_game_start_time']) - timedelta(hours=1)
                     for ticker in tickers)
    return tickers, first_lock


async def collect(pair: dict, original: dict, reader: KalshiReader, *,
                  now: datetime | None = None, clock_now=None) -> dict:
    """One later observation in at most ten unsigned exact-ticker batches."""
    tickers, first_lock = _frozen(pair, original)
    clock_now = clock_now or (lambda: datetime.now(timezone.utc))
    now = now or clock_now()
    decision = max(clock(pair['completed_at']),
                   *(clock(pair[key]['frozen_at']) for key, _ in POLICIES.values()))
    if now.utcoffset() is None or not decision < now < first_lock:
        raise ValueError('Exact quote capture must follow decision and precede first lock')
    pages = []
    for offset in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[offset:offset+BATCH_SIZE]
        started = clock_now()
        try:
            body = await reader.quoted_markets(batch)
            page = dict(tickers=batch, request_started_at=started.isoformat(),
                        received_at=clock_now().isoformat(), body=body)
        except Exception as exc:
            page = dict(tickers=batch, request_started_at=started.isoformat(),
                        received_at=clock_now().isoformat(), error_type=type(exc).__name__)
        pages.append(page)
    captured = clock_now()
    evidence = dict(protocol=VERSION, captured_at=captured.isoformat(),
                    pair_sha256=digest(pair),
                    original_evidence_sha256=original['summary']['evidence_sha256'],
                    requested_tickers=tickers, pages=pages)
    return dict(evidence=evidence, evidence_sha256=digest(evidence))


def _side_asks(market: dict) -> dict[str, tuple[Decimal, Decimal] | None]:
    result = {}
    for side, bid_key, size_key, ask_key in (
            ('yes', 'no_bid_dollars', 'yes_ask_size_fp', 'yes_ask_dollars'),
            ('no', 'yes_bid_dollars', 'yes_bid_size_fp', 'no_ask_dollars')):
        if not all(isinstance(market.get(key), str) for key in (bid_key, size_key, ask_key)):
            raise ValueError('Missing fixed-point quote fields')
        bid, size, reported = (Decimal(market[key]) for key in (bid_key, size_key, ask_key))
        if not all(value.is_finite() for value in (bid, size, reported)):
            raise ValueError('Invalid fixed-point quote')
        if bid == size == 0 and reported in (0, 1):
            result[side] = None
            continue
        ask = 1 - bid
        if not 0 < bid < 1 or size <= 0 or reported != ask:
            raise ValueError('Inconsistent displayed ask')
        result[side] = (ask, size)
    if all(result.values()) and result['yes'][0] + result['no'][0] < 1:
        raise ValueError('Crossed displayed asks')
    return result


def _market_state(market: dict, old: dict, side: str) -> tuple[str, Decimal | None]:
    try:
        strike = market['custom_strike']
        rules = dict(primary=market['rules_primary'], secondary=market['rules_secondary'])
        identity_ok = (market['ticker'] == old['ticker']
                       and market['event_ticker'] == old['event_ticker']
                       and market['strike_type'] == old['strike_type']
                       and market['primary_participant_key'] == 'football_player'
                       and Decimal(str(market['floor_strike'])) == Decimal(old['line'])
                       and strike['football_player'] == old['player_target_id']
                       and strike['football_team'] == old['team_target_id']
                       and ('market_occurrence_time' not in old or
                            clock(market['occurrence_datetime']) ==
                            clock(old['market_occurrence_time']))
                       and hashlib.sha256(json.dumps(
                           rules, sort_keys=True, allow_nan=False).encode()).hexdigest()
                       == old['rules_sha256'])
    except (KeyError, ValueError, TypeError, InvalidOperation):
        identity_ok = False
    if not identity_ok:
        return 'identity_changed', None
    if market.get('status') not in ('active', 'open'):
        return 'not_open', None
    try:
        ask = _side_asks(market)[side]
    except (KeyError, ValueError, TypeError, InvalidOperation):
        return 'invalid_quote', None
    if ask is None:
        return 'side_unquoted', None
    if ask[1] < 1:
        return 'side_undersized', None
    return 'prelock_exact_ask', ask[0]


def evaluate(pair: dict, original: dict, receipt: dict, *, policy: str = 'role') -> dict:
    if policy not in POLICIES:
        raise ValueError('Unknown frozen ask policy')
    tickers, _ = _frozen(pair, original)
    evidence = receipt['evidence']
    if (evidence.get('protocol') != VERSION or receipt.get('evidence_sha256') != digest(evidence)
            or evidence.get('pair_sha256') != digest(pair)
            or evidence.get('original_evidence_sha256') != original['summary']['evidence_sha256']
            or evidence.get('requested_tickers') != tickers):
        raise ValueError('Later exact-ticker receipt integrity failed')
    pages = evidence['pages']
    if not isinstance(pages, list) or len(pages) != (len(tickers)+BATCH_SIZE-1)//BATCH_SIZE:
        raise ValueError('Later exact-ticker page count changed')
    captured = clock(evidence['captured_at'])
    decision = max(clock(pair['completed_at']),
                   *(clock(pair[key]['frozen_at']) for key, _ in POLICIES.values()))
    by_ticker = {}
    for offset, page in enumerate(pages):
        batch = tickers[offset*BATCH_SIZE:(offset+1)*BATCH_SIZE]
        started, received = clock(page['request_started_at']), clock(page['received_at'])
        if page['tickers'] != batch or not decision < started <= received <= captured:
            raise ValueError('Later exact-ticker request chronology or scope changed')
        if 'error_type' in page:
            if 'body' in page or not isinstance(page['error_type'], str):
                raise ValueError('Malformed unavailable exact-ticker page')
            for ticker in batch:
                by_ticker[ticker] = (received, None, 'batch_unavailable')
            continue
        body = page['body']
        markets = body.get('markets') if isinstance(body, dict) else None
        if (not isinstance(markets, list) or body.get('cursor') not in (None, '')
                or any(not isinstance(market, dict) for market in markets)):
            raise ValueError('Incomplete or invalid exact-ticker response')
        returned = [market.get('ticker') for market in markets]
        if (len(markets) > len(batch) or len(set(returned)) != len(returned)
                or not set(returned) <= set(batch)):
            raise ValueError('Extra or duplicate exact-ticker response')
        lookup = {market['ticker']: market for market in markets}
        for ticker in batch:
            by_ticker[ticker] = (received, lookup.get(ticker), 'missing_exact_contract')
    pre, _ = preoutcome(pair, original, policy=policy)
    candidates = pair[POLICIES[policy][0]]['candidates']
    originals = {row['ticker']: row for row in original['evidence']['sources']['kalshi']['prop_inventory']['quotes']}
    counts: Counter[str] = Counter()
    changes: list[Decimal] = []
    games: dict[str, list[Decimal]] = defaultdict(list)
    rows = []
    for candidate in candidates:
        ticker = candidate['ticker']
        received, market, missing_state = by_ticker[ticker]
        old = originals[ticker]
        if received >= clock(old['scheduled_game_start_time']) - timedelta(hours=1):
            state, price = 'after_board_lock', None
        elif market is None:
            state, price = missing_state, None
        else:
            state, price = _market_state(market, old, candidate['side'])
        change = price-Decimal(candidate['displayed_ask']) if price is not None else None
        counts[state] += 1
        if change is not None:
            changes.append(change)
            games[candidate['milestone_id']].append(change)
        rows.append(dict(ticker=ticker, side=candidate['side'], state=state,
                         ask_change=str(change) if change is not None else None))
    if sum(counts.values()) != pre['candidates']:
        raise AssertionError('Frozen candidate denominator changed')
    game_means = [sum(values)/len(values) for values in games.values()]
    game_interval = _interval({game: (float(sum(values)/len(values)), 1.0)
                               for game, values in games.items()})
    return dict(protocol=VERSION, policy=policy, frozen_candidates=pre['candidates'],
                frozen_games=pre['candidate_games'],
                frozen_candidates_sha256=pre['candidates_sha256'],
                later_receipt_sha256=receipt['evidence_sha256'],
                later_captured_at=evidence['captured_at'],
                full_candidate_state_counts=dict(sorted(counts.items())),
                candidate_state_rows_sha256=digest(rows),
                prelock_matched_candidates=len(changes), prelock_matched_games=len(games),
                complete_candidate_markout=len(changes) == pre['candidates'],
                matched_subset_game_cluster_95=game_interval,
                side_ask_up=sum(value > 0 for value in changes),
                side_ask_down=sum(value < 0 for value in changes),
                side_ask_unchanged=sum(value == 0 for value in changes),
                mean_side_ask_change=str(sum(changes)/len(changes)) if changes else None,
                equal_game_mean_side_ask_change=(str(sum(game_means)/len(game_means))
                                                 if game_means else None),
                actual_fills_verified=False, closing_line_verified=False,
                edge_established=False, qualified_picks=0, roi=None,
                execution_ready=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', type=Path, required=True)
    parser.add_argument('--original-market-archive', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, help='Evaluate this prior exact-ticker capture')
    parser.add_argument('--preflight', action='store_true',
                        help='Validate frozen inputs and print scope without a network request')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not args.preflight and args.output is None:
        parser.error('--output is required for capture or evaluation')
    if args.output and (args.output.exists() or args.output.is_symlink()):
        parser.error('Output already exists')
    pair = _load(args.pair, MAX_PAIR_BYTES)
    original = _load(args.original_market_archive, MAX_ARCHIVE_BYTES)
    if args.preflight:
        tickers, first_lock = _frozen(pair, original)
        batches=(len(tickers)+BATCH_SIZE-1)//BATCH_SIZE
        print(json.dumps(dict(protocol=VERSION, exact_tickers=len(tickers),
                              request_batches=batches,
                              max_get_attempts_with_retries=batches*(len(READ_RETRY_DELAYS)+1),
                              first_lock_at=first_lock.isoformat())))
        return
    if args.receipt:
        receipt = _load(args.receipt, MAX_RECEIPT_BYTES)
        result = {policy: evaluate(pair, original, receipt, policy=policy) for policy in POLICIES}
    else:
        async def run() -> dict:
            async with KalshiReader() as reader:
                return await collect(pair, original, reader)
        result = asyncio.run(run())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
    if args.receipt:
        print(json.dumps({policy: result[policy]['full_candidate_state_counts']
                          for policy in POLICIES}, sort_keys=True))
    else:
        print(json.dumps(dict(protocol=VERSION, tickers=len(result['evidence']['requested_tickers']),
                              pages=len(result['evidence']['pages']),
                              evidence_sha256=result['evidence_sha256'])))


if __name__ == '__main__':
    main()
