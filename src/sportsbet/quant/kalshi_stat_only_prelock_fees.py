"""Unsigned prelock fee metadata for the frozen NFL paper cohort.

A separate, free public-data receipt. No quotes, orders, bets, or account calls.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from sportsbet.arbitrage.kalshi_fees import fee_terms
from sportsbet.ingestion.kalshi import KalshiReader
from sportsbet.market_watch import prop_fee_context
from sportsbet.quant.clock_attestation import attest
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_stat_only_forward_eval import _pinned, preflight
from sportsbet.quant.kalshi_stat_only_prelock import scope, within_window, validate_clock_proof

VERSION = 'kalshi-nfl-stat-only-prelock-fees-v1'
MAX_RAW_BYTES = 2_000_000


def identities(market: dict, forecast: dict, decisions: dict,
               kickoff: datetime) -> tuple[list[dict], dict[str, str]]:
    selected, _ = scope(forecast, decisions, kickoff)
    quotes = market['evidence']['sources']['kalshi']['prop_inventory']['quotes']
    by_ticker = {row['ticker']: row for row in quotes}
    if len(by_ticker) != len(quotes):
        raise ValueError('Duplicate original quote')
    events = {}
    for row in selected:
        quote = by_ticker.get(row['ticker'])
        if (not isinstance(quote, dict)
                or quote.get('milestone_id') != row['milestone_id']
                or not isinstance(quote.get('event_ticker'), str)
                or not isinstance(quote.get('series_ticker'), str)
                or not row['ticker'].startswith(quote['event_ticker'] + '-')):
            raise ValueError('Frozen fee event identity changed')
        event, series = quote['event_ticker'], quote['series_ticker']
        if event in events and events[event] != series:
            raise ValueError('Ambiguous event fee series')
        events[event] = series
    if not 1 <= len(events) <= 100:
        raise ValueError('Unbounded fee event scope')
    return selected, dict(sorted(events.items()))


async def capture(market: dict, forecast: dict, decisions: dict,
                  kickoff: datetime, reader: KalshiReader, *,
                  now=None, clock_proof=None) -> dict:
    selected, events = identities(market, forecast, decisions, kickoff)
    now = now or (lambda: datetime.now(timezone.utc))
    started = now()
    if (not within_window(started, kickoff)
            or started <= clock(decisions['decided_at'])):
        raise ValueError('Outside fixed prelock fee window')
    validate_clock_proof(clock_proof, started, kickoff)
    sources = {}
    semaphore = asyncio.Semaphore(8)

    async def read_series(series: str) -> dict[str, dict]:
        related = [event for event, name in events.items() if name == series]
        try:
            async with semaphore:
                series_data, series_changes = await asyncio.gather(
                    reader.series(series), reader.series_fee_changes(series))
        except Exception as exc:
            return {event: {'status': 'unavailable',
                            'error_type': type(exc).__name__}
                    for event in related}

        async def read_event(event: str) -> tuple[str, dict]:
            try:
                async with semaphore:
                    event_changes = await reader.event_fee_changes(event)
                received = now()
                if not within_window(received, kickoff):
                    raise ValueError('Fee capture exceeded window')
                raw = {'series': series_data, 'series_changes': series_changes,
                       'event_changes': event_changes}
                if len(json.dumps(raw, allow_nan=False).encode()) > MAX_RAW_BYTES:
                    raise ValueError('Fee source exceeds size bound')
                context = prop_fee_context(series_data, series_changes,
                                           event, event_changes, received)
                fee_terms(context, event, received)
                return event, {'status': 'observed', 'raw': raw,
                               'context': context}
            except Exception as exc:
                return event, {'status': 'unavailable',
                               'error_type': type(exc).__name__}

        return dict(await asyncio.gather(*(read_event(event) for event in related)))

    by_series = await asyncio.gather(
        *(read_series(series) for series in sorted(set(events.values()))))
    for result in by_series:
        sources.update(result)
    captured = now()
    if not within_window(captured, kickoff):
        raise ValueError('Fee capture exceeded window')
    evidence = {'protocol': VERSION, 'kickoff': kickoff.isoformat(),
                'market_sha256': digest(market),
                'forecast_sha256': digest(forecast),
                'decisions_sha256': digest(decisions),
                'candidate_rows_sha256': digest(selected), 'events': events,
                'request_started_at': started.isoformat(),
                'captured_at': captured.isoformat(),
                'clock_attestation': clock_proof, 'sources': sources}
    return {'evidence': evidence, 'evidence_sha256': digest(evidence)}


def evaluate(market: dict, forecast: dict, decisions: dict,
             receipt: dict) -> dict:
    evidence = receipt['evidence']
    kickoff = clock(evidence['kickoff'])
    selected, events = identities(market, forecast, decisions, kickoff)
    started = clock(evidence['request_started_at'])
    captured = clock(evidence['captured_at'])
    if (evidence.get('protocol') != VERSION
            or receipt.get('evidence_sha256') != digest(evidence)
            or evidence.get('market_sha256') != digest(market)
            or evidence.get('forecast_sha256') != digest(forecast)
            or evidence.get('decisions_sha256') != digest(decisions)
            or evidence.get('candidate_rows_sha256') != digest(selected)
            or evidence.get('events') != events
            or not isinstance(evidence.get('sources'), dict)
            or set(evidence['sources']) != set(events)
            or not within_window(started, kickoff)
            or not within_window(captured, kickoff)
            or not started <= captured):
        raise ValueError('Fee receipt scope or commitment changed')
    validate_clock_proof(evidence.get('clock_attestation'), started, kickoff)
    counts = Counter()
    for event, series in events.items():
        item = evidence['sources'][event]
        if item.get('status') == 'unavailable':
            if (set(item) != {'status', 'error_type'}
                    or not isinstance(item['error_type'], str)
                    or not item['error_type'] or len(item['error_type']) > 100):
                raise ValueError('Malformed fee failure')
            counts['unavailable'] += 1
            continue
        if item.get('status') != 'observed' or set(item) != {'status', 'raw', 'context'}:
            raise ValueError('Malformed fee source')
        raw, context = item['raw'], item['context']
        received = clock(context['received_at'])
        if (not started <= received <= captured
                or context['series']['ticker'] != series
                or len(json.dumps(raw, allow_nan=False).encode()) > MAX_RAW_BYTES
                or prop_fee_context(raw['series'], raw['series_changes'],
                                    event, raw['event_changes'], received) != context):
            raise ValueError('Fee source chronology or proof changed')
        fee_terms(context, event, received)
        counts['observed'] += 1
    return {'protocol': VERSION, 'kickoff': evidence['kickoff'],
            'frozen_candidates': len(selected),
            'frozen_games': len({row['milestone_id'] for row in selected}),
            'fee_events': len(events), 'fee_event_counts': dict(sorted(counts.items())),
            'receipt_sha256': receipt['evidence_sha256'],
            'quoted_prices_collected': False, 'fills_verified': False,
            'fee_adjusted_return': None, 'edge_established': False,
            'qualified_picks': 0}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair', 'market', 'forecast', 'quotes', 'decisions'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--kickoff', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if (args.output.exists() or args.output.is_symlink()
            or args.report.exists() or args.report.is_symlink()):
        parser.error('Fee receipt or report already exists')
    pair, market, forecast, quotes, decisions = (
        _pinned(getattr(args, name), name) for name in
        ('pair', 'market', 'forecast', 'quotes', 'decisions'))
    preflight(pair, market, forecast, quotes, decisions,
              args.source_dir, args.schedule)
    kickoff = clock(args.kickoff)
    identities(market, forecast, decisions, kickoff)
    if not within_window(datetime.now(timezone.utc), kickoff):
        parser.error('Outside fixed prelock fee window')
    proof = await attest()

    class UnsignedReader(KalshiReader):
        def _headers(self, path: str) -> dict[str, str]:
            raise RuntimeError('Authenticated request forbidden')

    async with UnsignedReader() as reader:
        receipt = await capture(market, forecast, decisions, kickoff,
                                reader, clock_proof=proof)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2, allow_nan=False)
    try:
        report = evaluate(market, forecast, decisions, receipt)
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        report = {'protocol': VERSION, 'kickoff': kickoff.isoformat(),
                  'receipt_sha256': receipt['evidence_sha256'],
                  'evaluation': 'unavailable', 'error_type': type(exc).__name__,
                  'edge_established': False, 'qualified_picks': 0}
        with args.report.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
        raise
    with args.report.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    asyncio.run(main())
