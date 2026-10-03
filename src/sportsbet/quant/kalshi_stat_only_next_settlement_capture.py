"""One unsigned full-denominator venue result read for a committed NFL paper pair."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path

from sportsbet.quant import kalshi_market_settlement as venue
from sportsbet.quant import kalshi_stat_only_next_eval as next_eval
from sportsbet.quant.clock_attestation import attest
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_pair_capture import unpack
from sportsbet.quant.kalshi_stat_only_settlement_capture import (
    UnsignedReader, validate_clock_proof)

VERSION = next_eval.SETTLEMENT_VERSION


async def capture(inputs: dict[str, str], source_dir: Path, commitment: dict,
                  reader: UnsignedReader, proof: dict, *, now: datetime) -> tuple[dict, dict]:
    values, pre, _ = next_eval.committed_preflight(inputs, source_dir, commitment)
    now = clock(now.isoformat())
    eligible = clock(pre['first_eligible_settlement_at'])
    if now < eligible:
        raise ValueError('Full-cohort venue result gate is premature')
    validate_clock_proof(proof, eligible, now)
    cohort, _ = unpack(values['pair'])
    if len(venue.verify_cohort(values['market'], cohort)) != pre['original_market_contracts']:
        raise ValueError('Exact venue contract denominator changed')
    result = await venue.collect(values['market'], cohort, reader, now=now)
    receipt = dict(result, protocol=VERSION, clock_proof=proof,
                   pregame_commitment_sha256=digest(commitment),
                   original_market_contracts=pre['original_market_contracts'],
                   first_eligible_settlement_at=eligible.isoformat(),
                   captured_at=datetime.now(timezone.utc).isoformat(),
                   edge_established=False, qualified_picks=0,
                   execution_ready=False)
    receipt['record_sha256'] = digest(receipt)
    if len(json.dumps(receipt, allow_nan=False).encode()) > venue.MAX_INPUT_BYTES:
        raise ValueError('Full venue result receipt is unbounded')
    try:
        report = venue.audit(values['market'], cohort, receipt,
                             now=datetime.now(timezone.utc))
        if not isinstance(report, dict):
            raise TypeError('Venue audit report is not an object')
    except Exception as exc:
        report = dict(protocol=venue.VERSION, evaluation='unavailable',
                      error_type=type(exc).__name__,
                      selected_contracts=pre['original_market_contracts'],
                      settlement_evidence_sha256=receipt['evidence_sha256'],
                      edge_established=False, qualified_picks=0,
                      execution_ready=False)
    report.update(capture_protocol=VERSION,
                  capture_record_sha256=receipt['record_sha256'],
                  clock_checked_at=proof['checked_at'])
    return receipt, report


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in next_eval.LIMITS:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--commitment', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if (args.output.exists() or args.output.is_symlink()
            or args.report.exists() or args.report.is_symlink()):
        parser.error('Result output already exists; no venue read was made')
    inputs = {name: str(getattr(args, name)) for name in next_eval.LIMITS}
    commitment, _ = next_eval._input(args.commitment, 10_000)
    _, pre, _ = next_eval.committed_preflight(inputs, args.source_dir, commitment)
    if datetime.now(timezone.utc) < clock(pre['first_eligible_settlement_at']):
        parser.error('Before full-cohort venue result gate; no venue read was made')
    proof = await attest()
    async with UnsignedReader() as reader:
        receipt, report = await capture(inputs, args.source_dir, commitment,
                                        reader, proof, now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2, allow_nan=False)
    with args.report.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    if report.get('evaluation') == 'unavailable':
        raise ValueError('Raw venue evidence retained; aggregate audit unavailable')
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    asyncio.run(main())
