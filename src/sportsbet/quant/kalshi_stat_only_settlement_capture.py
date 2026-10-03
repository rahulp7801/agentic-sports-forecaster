"""One unsigned, exact-contract NFL stat-only venue result capture after all games.

This reads public Kalshi settlement metadata only. It cannot authenticate,
place orders, refresh prices, modify picks, or assert a profitable edge.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from sportsbet.ingestion.kalshi import KalshiReader
from sportsbet.quant import kalshi_stat_only_forward_eval as frozen
from sportsbet.quant import kalshi_market_settlement as venue
from sportsbet.quant.clock_attestation import (
    HOSTS, MAX_BETWEEN_HOST_OFFSETS_SECONDS, MAX_OFFSET_SECONDS,
    MAX_RTT_SECONDS, VERSION as CLOCK_VERSION, attest,
)
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_pair_capture import unpack

VERSION = 'kalshi-nfl-stat-only-unsigned-settlement-capture-v1'


class UnsignedReader(KalshiReader):
    def _headers(self, path: str) -> dict[str, str]:
        raise RuntimeError('Authenticated Kalshi request forbidden')

    async def settled_markets(self, tickers: list[str], *, historical: bool) -> dict:
        if historical:
            raise ValueError('Historical or additional venue query forbidden')
        # The public exact-ticker endpoint returns every status without a filter.
        # Preserve closed/unreturned states rather than prefiltering the denominator.
        return await self.quoted_markets(tickers)


def validate_clock_proof(proof: dict, eligible: datetime, now: datetime) -> None:
    """Replay independent clocks before any public venue result request."""
    if (not isinstance(proof, dict) or proof.get('protocol') != CLOCK_VERSION
            or proof.get('local_clock_acceptable') is not True
            or not isinstance(proof.get('observations'), list)
            or len(proof['observations']) != len(HOSTS)):
        raise ValueError('Prospective result clock proof missing')
    checked = clock(proof['checked_at'])
    if not eligible <= checked <= now or (now-checked).total_seconds() > 120:
        raise ValueError('Prospective result clock proof stale or premature')
    offsets = []
    for host, row in zip(HOSTS, proof['observations'], strict=True):
        if (not isinstance(row, dict) or row.get('host') != host
                or row.get('http_status') != 200):
            raise ValueError('Prospective result clock host or status changed')
        started, received, server = (clock(row[key]) for key in
                                     ('request_started_at', 'response_received_at', 'server_date'))
        rtt = (received-started).total_seconds()
        offset = (server-(started+(received-started)/2)).total_seconds()
        age = row.get('age')
        uncached = (age is None or (type(age) is str and age == '0')
                    or (type(age) is int and age == 0))
        reported_rtt, reported_offset = row.get('rtt_seconds'), row.get('server_minus_local_seconds')
        if (not started <= received <= checked or not 0 <= rtt <= MAX_RTT_SECONDS
                or not math.isfinite(offset) or abs(offset) > MAX_OFFSET_SECONDS
                or not uncached or type(reported_rtt) not in (int, float)
                or type(reported_offset) not in (int, float)
                or not math.isfinite(reported_rtt) or not math.isfinite(reported_offset)
                or abs(reported_rtt-rtt) > .001
                or abs(reported_offset-offset) > .001):
            raise ValueError('Prospective result clock observation changed')
        offsets.append(offset)
    if abs(offsets[0]-offsets[1]) > MAX_BETWEEN_HOST_OFFSETS_SECONDS:
        raise ValueError('Prospective result clock hosts disagree')


async def capture(pair: dict, market: dict, forecast: dict, quotes: dict,
                  decisions: dict, source_dir: Path, schedule: Path,
                  reader: KalshiReader, clock_proof: dict, *, now: datetime) -> tuple[dict, dict]:
    pre, _ = frozen.preflight(pair, market, forecast, quotes, decisions,
                              source_dir, schedule)
    now = clock(now.isoformat())
    eligible = clock(pre['first_eligible_settlement_at'])
    if now < eligible:
        raise ValueError('Exact result capture is premature')
    validate_clock_proof(clock_proof, eligible, now)
    cohort, _ = unpack(pair)
    if len(venue.verify_cohort(market, cohort)) != pre['original_market_contracts']:
        raise ValueError('Original contract denominator changed')
    result = await venue.collect(market, cohort, reader, now=now)
    receipt = dict(result, protocol=VERSION, clock_proof=clock_proof,
                   original_market_contracts=pre['original_market_contracts'],
                   first_eligible_settlement_at=eligible.isoformat(),
                   captured_at=datetime.now(timezone.utc).isoformat(),
                   edge_established=False, qualified_picks=0, execution_ready=False)
    receipt['record_sha256'] = digest(receipt)
    if len(json.dumps(receipt, allow_nan=False).encode()) > venue.MAX_INPUT_BYTES:
        raise ValueError('Full-denominator venue receipt is unbounded')
    try:
        report = venue.audit(market, cohort, receipt, now=datetime.now(timezone.utc))
        if not isinstance(report, dict):
            raise TypeError('Venue audit report is not an object')
    except Exception as exc:
        # Preserve bounded raw evidence and fail the task for any audit defect.
        report = dict(protocol=venue.VERSION, evaluation='unavailable',
            error_type=type(exc).__name__,
            selected_contracts=pre['original_market_contracts'],
            settlement_evidence_sha256=receipt['evidence_sha256'],
            edge_established=False, qualified_picks=0, execution_ready=False)
    report.update(capture_protocol=VERSION,
                  capture_record_sha256=receipt['record_sha256'],
                  clock_checked_at=clock_proof['checked_at'])
    return receipt, report


def _save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair','market','forecast','quotes','decisions'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if (args.output.exists() or args.output.is_symlink()
            or args.report.exists() or args.report.is_symlink()):
        parser.error('Settlement output already exists; no venue read was made')
    pair, market, forecast, quotes, decisions = (
        frozen._pinned(getattr(args,name),name) for name in
        ('pair','market','forecast','quotes','decisions'))
    # No public venue request until the full frozen preflight and clock gate pass.
    pre, _ = frozen.preflight(pair, market, forecast, quotes, decisions,
                              args.source_dir, args.schedule)
    if datetime.now(timezone.utc) < clock(pre['first_eligible_settlement_at']):
        parser.error('Before the full-cohort settlement gate; no venue read was made')
    proof = await attest()
    async with UnsignedReader() as reader:
        receipt, report = await capture(pair,market,forecast,quotes,decisions,
                                        args.source_dir,args.schedule,reader,proof,
                                        now=datetime.now(timezone.utc))
    # Preserve the raw full-denominator venue evidence even if later scoring fails.
    _save(args.output, receipt)
    _save(args.report, report)
    if report.get('evaluation') == 'unavailable':
        raise ValueError('Venue evidence retained but aggregate audit unavailable')
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    asyncio.run(main())
