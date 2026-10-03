"""One free pregame re-observation of pinned NFL injury and roster archives.

No Odds API, credentials, prices, orders, or prediction changes. An unchanged
asset is copied from the already retained baseline rather than downloaded.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import httpx

from sportsbet.quant.clock_attestation import (
    HOSTS, MAX_BETWEEN_HOST_OFFSETS_SECONDS, MAX_OFFSET_SECONDS,
    MAX_RTT_SECONDS, VERSION as CLOCK_VERSION, attest,
)
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_pair_sources import download_asset
from sportsbet.quant import kalshi_stat_only_teammate_context as context
from sportsbet.quant import kalshi_stat_only_roster_audit as roster

VERSION = 'kalshi-nfl-stat-only-context-refresh-v1'
WINDOW_START = '2026-10-04T09:30:00+00:00'
WINDOW_END = '2026-10-04T11:30:00+00:00'
MAX_METADATA_BYTES = 500_000
SOURCES = (
    ('injuries', 'injuries_2026.parquet', context.INJURY_SOURCE_URL,
     context.INJURY_SHA256, context.INJURY_ASSET_UPDATED_AT),
    ('weekly_rosters', 'roster_weekly_2026.parquet', roster.ROSTER_URL,
     roster.ROSTER_SHA256, roster.ROSTER_ASSET_UPDATED_AT),
)


def validate_asset(metadata: dict, tag: str, filename: str, url: str,
                   baseline_hash: str, baseline_updated: str, now: datetime) -> dict:
    if not isinstance(metadata, dict) or not isinstance(metadata.get('assets'), list):
        raise ValueError('Release metadata unavailable')
    matches = [item for item in metadata['assets'] if item.get('name') == filename]
    if len(matches) != 1:
        raise ValueError('Exact current-season asset missing or ambiguous')
    item = matches[0]
    raw_hash = item.get('digest')
    if (item.get('state') != 'uploaded' or not isinstance(item.get('id'), int)
            or not isinstance(item.get('size'), int) or not 0 < item['size'] <= 2_000_000
            or item.get('browser_download_url') != url
            or not isinstance(raw_hash, str) or not raw_hash.startswith('sha256:')
            or len(raw_hash) != 71):
        raise ValueError('Untrusted or unbounded NFL release asset')
    updated = clock(item['updated_at'])
    if not clock(baseline_updated) <= updated <= now:
        raise ValueError('Current asset chronology unavailable')
    if updated == clock(baseline_updated) and raw_hash[7:] != baseline_hash:
        raise ValueError('Original asset timestamp has changed bytes')
    return dict(tag=tag, filename=filename, url=url, id=item['id'],
                size=item['size'], updated_at=updated.isoformat(), sha256=raw_hash[7:],
                changed_from_baseline=raw_hash[7:] != baseline_hash)


def validate_clock_proof(proof: dict, recorded: datetime, *, max_age_seconds: int) -> None:
    """Replay both independent clocks before source reads and after capture."""
    if (not isinstance(proof, dict) or proof.get('protocol') != CLOCK_VERSION
            or proof.get('local_clock_acceptable') is not True
            or not isinstance(proof.get('observations'), list)
            or len(proof['observations']) != len(HOSTS)):
        raise ValueError('Refresh clock proof missing')
    checked = clock(proof['checked_at'])
    if (not clock(WINDOW_START) <= checked <= recorded
            or (recorded-checked).total_seconds() > max_age_seconds):
        raise ValueError('Refresh clock chronology changed')
    offsets = []
    for host, row in zip(HOSTS, proof['observations'], strict=True):
        if not isinstance(row, dict) or row.get('host') != host or row.get('http_status') != 200:
            raise ValueError('Refresh clock host changed')
        before, after, server = (clock(row[key]) for key in
                                 ('request_started_at','response_received_at','server_date'))
        rtt = (after-before).total_seconds()
        offset = (server-(before+(after-before)/2)).total_seconds()
        reported_rtt, reported_offset = row.get('rtt_seconds'), row.get('server_minus_local_seconds')
        age = row.get('age')
        uncached = age is None or (type(age) is str and age == '0') or (type(age) is int and age == 0)
        if (not before <= after <= checked or not 0 <= rtt <= MAX_RTT_SECONDS
                or not math.isfinite(offset) or abs(offset) > MAX_OFFSET_SECONDS
                or not uncached
                or type(reported_rtt) not in (int, float)
                or type(reported_offset) not in (int, float)
                or not math.isfinite(reported_rtt) or not math.isfinite(reported_offset)
                or abs(reported_rtt-rtt) > .001
                or abs(reported_offset-offset) > .001):
            raise ValueError('Refresh clock observation changed')
        offsets.append(offset)
    if abs(offsets[0]-offsets[1]) > MAX_BETWEEN_HOST_OFFSETS_SECONDS:
        raise ValueError('Refresh clock hosts disagree')


def stage(root: Path, baseline_dir: Path, context_receipt: dict,
          *, now: datetime, client: httpx.Client, clock_proof: dict) -> dict:
    now = clock(now.isoformat())
    if (root.exists() or root.is_symlink() or not clock(WINDOW_START) <= now < clock(WINDOW_END)
            or now >= clock(context_receipt['first_kickoff_at'])
            or context_receipt.get('record_sha256') != context.EXPECTED_RECORD_SHA256
            or digest({k:v for k,v in context_receipt.items() if k != 'record_sha256'})
                != context.EXPECTED_RECORD_SHA256
            or not isinstance(clock_proof, dict)):
        raise ValueError('Context refresh is not authorized by pregame time and receipt')
    validate_clock_proof(clock_proof, now, max_age_seconds=120)
    metadata_receipts = {}
    asset_receipts = {}
    staged_bytes = {}
    for tag, filename, url, baseline_hash, baseline_updated in SOURCES:
        response = client.get(
            f'https://api.github.com/repos/nflverse/nflverse-data/releases/tags/{tag}',
            headers={'Accept':'application/vnd.github+json', 'Cache-Control':'no-cache'})
        if response.is_redirect:
            raise ValueError('Release metadata redirect refused')
        response.raise_for_status()
        raw = response.content
        if not 0 < len(raw) <= MAX_METADATA_BYTES:
            raise ValueError('Release metadata unbounded')
        metadata = json.loads(raw)
        entry = validate_asset(metadata, tag, filename, url, baseline_hash, baseline_updated, now)
        metadata_receipts[tag] = dict(sha256=hashlib.sha256(raw).hexdigest(), raw=raw)
        if entry['changed_from_baseline']:
            content = download_asset(client, url, entry['sha256'])
            entry['retrieval'] = 'downloaded_changed_public_asset'
        else:
            path = baseline_dir / filename
            if path.is_symlink() or not path.is_file():
                raise ValueError('Original source unavailable for unchanged asset')
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != baseline_hash:
                raise ValueError('Original source changed')
            entry['retrieval'] = 'copied_pinned_baseline'
        if len(content) != entry['size']:
            raise ValueError('Asset size differs from release metadata')
        asset_receipts[tag] = entry
        staged_bytes[filename] = content
    recorded = datetime.now(timezone.utc)
    if not now <= recorded < clock(WINDOW_END) or recorded >= clock(context_receipt['first_kickoff_at']):
        raise ValueError('Source refresh finished after first kickoff')
    receipt = dict(protocol=VERSION, recorded_at=recorded.isoformat(),
                   window_start=WINDOW_START, window_end=WINDOW_END,
                   first_kickoff_at=context_receipt['first_kickoff_at'],
                   frozen_context_record_sha256=context.EXPECTED_RECORD_SHA256,
                   clock_proof=clock_proof, assets=asset_receipts,
                   release_metadata_sha256={k:v['sha256'] for k,v in metadata_receipts.items()},
                   edge_established=False, qualified_picks=0, execution_ready=False)
    receipt['record_sha256'] = digest(receipt)
    root.mkdir(parents=True, exist_ok=False)
    for filename, content in staged_bytes.items():
        with (root / filename).open('xb') as stream:
            stream.write(content)
    for tag, value in metadata_receipts.items():
        with (root / f'{tag}-release.json').open('xb') as stream:
            stream.write(value['raw'])
    with (root / 'receipt.json').open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2, allow_nan=False)
    return receipt


def verify(root: Path, context_receipt: dict) -> dict:
    """Replay receipt, raw metadata bytes, chronology, and both exact assets."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Refresh directory unavailable')
    path = root / 'receipt.json'
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 100_000:
        raise ValueError('Refresh receipt missing or unbounded')
    receipt = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(receipt, dict) or receipt.get('protocol') != VERSION
            or receipt.get('record_sha256') != digest({k:v for k,v in receipt.items()
                                                     if k != 'record_sha256'})
            or receipt.get('frozen_context_record_sha256') != context.EXPECTED_RECORD_SHA256
            or context_receipt.get('record_sha256') != context.EXPECTED_RECORD_SHA256
            or digest({k:v for k,v in context_receipt.items() if k != 'record_sha256'})
                != context.EXPECTED_RECORD_SHA256
            or receipt.get('first_kickoff_at') != context_receipt.get('first_kickoff_at')
            or receipt.get('window_start') != WINDOW_START or receipt.get('window_end') != WINDOW_END
            or set(receipt.get('assets', {})) != {row[0] for row in SOURCES}
            or set(receipt.get('release_metadata_sha256', {})) != {row[0] for row in SOURCES}):
        raise ValueError('Refresh receipt identity or scope changed')
    recorded = clock(receipt['recorded_at'])
    if not clock(WINDOW_START) <= recorded < clock(WINDOW_END) < clock(receipt['first_kickoff_at']):
        raise ValueError('Refresh receipt was not pregame')
    validate_clock_proof(receipt['clock_proof'], recorded, max_age_seconds=180)
    for tag, filename, url, baseline_hash, baseline_updated in SOURCES:
        meta_path, asset_path = root / f'{tag}-release.json', root / filename
        if (meta_path.is_symlink() or not meta_path.is_file()
                or not 0 < meta_path.stat().st_size <= MAX_METADATA_BYTES
                or asset_path.is_symlink() or not asset_path.is_file()
                or not 0 < asset_path.stat().st_size <= 2_000_000):
            raise ValueError('Refresh source missing or unbounded')
        raw = meta_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != receipt['release_metadata_sha256'][tag]:
            raise ValueError('Raw release metadata changed')
        entry = validate_asset(json.loads(raw), tag, filename, url,
                               baseline_hash, baseline_updated, recorded)
        expected = dict(entry, retrieval=('downloaded_changed_public_asset'
                                         if entry['changed_from_baseline'] else 'copied_pinned_baseline'))
        if expected != receipt['assets'][tag]:
            raise ValueError('Release asset manifest changed')
        asset = asset_path.read_bytes()
        if len(asset) != entry['size'] or hashlib.sha256(asset).hexdigest() != entry['sha256']:
            raise ValueError('Refresh asset bytes changed')
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context-receipt', type=Path, required=True)
    parser.add_argument('--baseline-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() or args.output_dir.is_symlink():
        parser.error('Exclusive context refresh output already exists')
    path = args.context_receipt
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 30_000_000:
        parser.error('Frozen context receipt missing or unbounded')
    receipt = json.loads(path.read_text(encoding='utf-8'))
    now = datetime.now(timezone.utc)
    if not clock(WINDOW_START) <= now < clock(WINDOW_END):
        parser.error('Outside one-time pregame context refresh window')
    proof = asyncio.run(attest())
    with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
        report = stage(args.output_dir, args.baseline_dir, receipt,
                       now=datetime.now(timezone.utc), client=client, clock_proof=proof)
    print(json.dumps({k:v for k,v in report.items() if k != 'clock_proof'}, sort_keys=True))


if __name__ == '__main__':
    main()
