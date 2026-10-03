"""One free exact-ticker prelock observation per frozen stat-only kickoff group.

This is an unfilled ask-movement diagnostic, not a closing line or an edge.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import math
from pathlib import Path

from sportsbet.ingestion.kalshi import KalshiReader
from sportsbet.quant.clock_attestation import HOSTS, VERSION as CLOCK_VERSION, attest
from sportsbet.quant.kalshi_exact_markout import _market_state
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_stat_only_forward_eval import _pinned, preflight

VERSION = 'kalshi-nfl-stat-only-prelock-ask-v1'
BATCH = 20
EARLIEST = timedelta(minutes=90)
LATEST = timedelta(minutes=70)


def scope(forecast: dict, decisions: dict, kickoff: datetime) -> tuple[list[dict], list[str]]:
    """Keep the original candidates fixed before observing a later price."""
    if kickoff.utcoffset() is None:
        raise ValueError('Kickoff must be timezone aware')
    starts = {row['ticker']: clock(row['scheduled_game_start_time'])
              for row in forecast['forecasts']}
    if (len(starts) != len(forecast['forecasts'])
            or decisions['model_forecast_sha256'] != forecast['forecast_sha256']
            or decisions['candidates_sha256'] != digest(decisions['candidates'])
            or len(decisions['candidates']) != decisions['candidates_count']):
        raise ValueError('Frozen decision scope changed')
    selected = [row for row in decisions['candidates'] if starts[row['ticker']] == kickoff]
    tickers = sorted(row['ticker'] for row in selected)
    if not selected or len(tickers) > 100 or len(set(tickers)) != len(tickers):
        raise ValueError('Empty, duplicate, or unbounded kickoff group')
    return selected, tickers


def within_window(moment: datetime, kickoff: datetime) -> bool:
    return moment.utcoffset() is not None and kickoff-EARLIEST <= moment < kickoff-LATEST


def validate_clock_proof(proof: dict, first_request: datetime, kickoff: datetime) -> None:
    """Retain check chronology; a server Date remains noncryptographic evidence."""
    if (not isinstance(proof, dict) or proof.get('protocol') != CLOCK_VERSION
            or proof.get('local_clock_acceptable') is not True
            or not isinstance(proof.get('observations'), list)
            or len(proof['observations']) != 2):
        raise ValueError('Prelock clock proof missing')
    checked = clock(proof['checked_at'])
    if (not within_window(checked, kickoff) or checked > first_request
            or (first_request-checked).total_seconds() > 120):
        raise ValueError('Prelock clock proof chronology changed')
    offsets = []
    for expected_host, row in zip(HOSTS, proof['observations'], strict=True):
        if not isinstance(row, dict) or row.get('host') != expected_host:
            raise ValueError('Prelock clock host changed')
        started, received = clock(row['request_started_at']), clock(row['response_received_at'])
        server = clock(row['server_date'])
        rtt = (received-started).total_seconds()
        offset = (server-(started+(received-started)/2)).total_seconds()
        age = row.get('age')
        uncached = age is None or (type(age) is str and age == '0') or (type(age) is int and age == 0)
        if (not started <= received <= checked or rtt > 2
                or row.get('http_status') != 200 or not uncached
                or type(row.get('rtt_seconds')) not in (int, float)
                or type(row.get('server_minus_local_seconds')) not in (int, float)
                or not math.isfinite(row['rtt_seconds'])
                or not math.isfinite(row['server_minus_local_seconds'])
                or abs(row['rtt_seconds']-rtt) > .001
                or abs(row['server_minus_local_seconds']-offset) > .001
                or abs(offset) > 2):
            raise ValueError('Prelock clock response invalid')
        offsets.append(offset)
    if abs(offsets[0]-offsets[1]) > 1.5:
        raise ValueError('Prelock clock sources disagree')


async def capture(original: dict, forecast: dict, decisions: dict, kickoff: datetime,
                  reader: KalshiReader, *, now=None, clock_proof=None) -> dict:
    """At most five unsigned public batches, all before the board lock."""
    selected, tickers = scope(forecast, decisions, kickoff)
    now = now or (lambda: datetime.now(timezone.utc))
    started = now()
    if not within_window(started, kickoff) or started <= clock(decisions['decided_at']):
        raise ValueError('Outside fixed prelock observation window')
    validate_clock_proof(clock_proof, started, kickoff)
    pages = []
    for offset in range(0, len(tickers), BATCH):
        batch = tickers[offset:offset+BATCH]
        request_time = now()
        if not within_window(request_time, kickoff):
            raise ValueError('Prelock window expired before exact quote request')
        try:
            body = await reader.quoted_markets(batch)
            page = dict(tickers=batch, request_started_at=request_time.isoformat(),
                        received_at=now().isoformat(), body=body)
        except Exception as exc:
            page = dict(tickers=batch, request_started_at=request_time.isoformat(),
                        received_at=now().isoformat(), error_type=type(exc).__name__)
        pages.append(page)
    captured = now()
    if not within_window(captured, kickoff):
        raise ValueError('Prelock window expired during capture')
    evidence = dict(protocol=VERSION, kickoff=kickoff.isoformat(),
        original_market_sha256=digest(original),
        forecast_receipt_sha256=digest(forecast), decision_receipt_sha256=digest(decisions),
        candidate_rows_sha256=digest(selected), requested_tickers=tickers,
        captured_at=captured.isoformat(), clock_attestation=clock_proof, pages=pages)
    return dict(evidence=evidence, evidence_sha256=digest(evidence))


def evaluate(original: dict, forecast: dict, decisions: dict, receipt: dict) -> dict:
    """Score every fixed candidate, including missing/invalid later quotes."""
    evidence = receipt['evidence']
    kickoff = clock(evidence['kickoff'])
    selected, tickers = scope(forecast, decisions, kickoff)
    pages = evidence['pages']
    if (evidence.get('protocol') != VERSION
            or receipt.get('evidence_sha256') != digest(evidence)
            or evidence.get('original_market_sha256') != digest(original)
            or evidence.get('forecast_receipt_sha256') != digest(forecast)
            or evidence.get('decision_receipt_sha256') != digest(decisions)
            or evidence.get('candidate_rows_sha256') != digest(selected)
            or evidence.get('requested_tickers') != tickers
            or not isinstance(pages, list) or len(pages) != (len(tickers)+BATCH-1)//BATCH
            or not within_window(clock(evidence['captured_at']), kickoff)):
        raise ValueError('Prelock receipt commitment or scope changed')
    validate_clock_proof(evidence.get('clock_attestation'),
                         clock(pages[0]['request_started_at']), kickoff)
    observed = {}
    for index, page in enumerate(pages):
        batch = tickers[index*BATCH:(index+1)*BATCH]
        started, received = clock(page['request_started_at']), clock(page['received_at'])
        if (page.get('tickers') != batch or not within_window(started, kickoff)
                or not started <= received <= clock(evidence['captured_at'])
                or received <= clock(decisions['decided_at'])):
            raise ValueError('Prelock request chronology changed')
        if 'error_type' in page:
            if 'body' in page or not isinstance(page['error_type'], str):
                raise ValueError('Conflicting prelock page')
            observed.update({ticker: (None, 'batch_unavailable') for ticker in batch})
            continue
        body = page['body']
        markets = body.get('markets') if isinstance(body, dict) else None
        if (not isinstance(markets, list) or body.get('cursor') not in (None, '')
                or any(not isinstance(market, dict) for market in markets)):
            raise ValueError('Incomplete prelock response')
        found = [market.get('ticker') for market in markets]
        if len(found) != len(set(found)) or not set(found) <= set(batch):
            raise ValueError('Duplicate or extra prelock quote')
        by_ticker = {market['ticker']: market for market in markets}
        observed.update({ticker: (by_ticker.get(ticker), 'missing_exact_contract')
                         for ticker in batch})
    originals = {row['ticker']: row for row in
        original['evidence']['sources']['kalshi']['prop_inventory']['quotes']}
    counts = Counter()
    changes = []
    games = defaultdict(list)
    rows = []
    for candidate in selected:
        ticker = candidate['ticker']
        market, missing_state = observed[ticker]
        state, ask = (missing_state, None) if market is None else _market_state(
            market, originals[ticker], candidate['side'])
        change = ask-Decimal(candidate['displayed_ask']) if ask is not None else None
        counts[state] += 1
        if change is not None:
            changes.append(change)
            games[candidate['milestone_id']].append(change)
        rows.append(dict(ticker=ticker, state=state,
                         ask_change=str(change) if change is not None else None))
    if sum(counts.values()) != len(selected):
        raise AssertionError('Frozen candidate denominator changed')
    game_means = [sum(values)/len(values) for values in games.values()]
    return dict(protocol=VERSION, kickoff=kickoff.isoformat(),
        frozen_candidates=len(selected), frozen_games=len({r['milestone_id'] for r in selected}),
        later_receipt_sha256=receipt['evidence_sha256'],
        candidate_state_counts=dict(sorted(counts.items())), state_rows_sha256=digest(rows),
        matched_candidates=len(changes), matched_games=len(games),
        complete_markout=len(changes)==len(selected),
        side_ask_up=sum(change>0 for change in changes),
        side_ask_down=sum(change<0 for change in changes),
        side_ask_unchanged=sum(change==0 for change in changes),
        mean_side_ask_change=str(sum(changes)/len(changes)) if changes else None,
        equal_game_mean_side_ask_change=str(sum(game_means)/len(game_means)) if game_means else None,
        actual_fills_verified=False, closing_line_verified=False, edge_established=False,
        qualified_picks=0, roi=None, clv=None, execution_ready=False)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair', 'market', 'forecast', 'quotes', 'decisions'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--kickoff', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if (args.output.exists() or args.output.is_symlink()
            or args.report.exists() or args.report.is_symlink()):
        parser.error('Receipt or report output already exists')
    pair, market, forecast, quotes, decisions = (
        _pinned(getattr(args, name), name) for name in
        ('pair', 'market', 'forecast', 'quotes', 'decisions'))
    preflight(pair, market, forecast, quotes, decisions, args.source_dir, args.schedule)
    kickoff = clock(args.kickoff)
    scope(forecast, decisions, kickoff)
    if not within_window(datetime.now(timezone.utc), kickoff):
        parser.error('Outside fixed prelock observation window')
    proof = await attest()
    class UnsignedReader(KalshiReader):
        def _headers(self, path: str) -> dict[str, str]:
            raise RuntimeError('Authenticated request forbidden')
    async with UnsignedReader() as reader:
        receipt = await capture(market, forecast, decisions, kickoff, reader, clock_proof=proof)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2, allow_nan=False)
    try:
        report = evaluate(market, forecast, decisions, receipt)
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        report = dict(protocol=VERSION, kickoff=kickoff.isoformat(),
            frozen_candidates=len(scope(forecast, decisions, kickoff)[0]),
            later_receipt_sha256=receipt['evidence_sha256'],
            evaluation='unavailable', error_type=type(exc).__name__,
            edge_established=False, qualified_picks=0, roi=None, clv=None)
        with args.report.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
        raise
    with args.report.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    asyncio.run(main())
