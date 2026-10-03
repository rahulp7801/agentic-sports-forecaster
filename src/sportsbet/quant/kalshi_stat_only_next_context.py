"""Pregame, free NFL availability source receipt for the next paper cohort.

This diagnostic never changes forecasts, paper decisions, or consumer picks.
An unavailable source is recorded explicitly instead of silently becoming a
negative injury report. Individual injury rows have no update timestamps.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path

import httpx

from sportsbet.quant.kalshi_market_cohort import clock
from sportsbet.quant.kalshi_pair_sources import download_asset
from sportsbet.quant.kalshi_stat_only_context_refresh import (
    MAX_METADATA_BYTES, SOURCES, validate_asset,
)

VERSION = 'kalshi-nfl-stat-only-next-context-v1'


def capture(root: Path, *, now: datetime, client: httpx.Client) -> dict:
    if root.exists() or root.is_symlink() or now.utcoffset() is None:
        raise ValueError('Context receipt output must be exclusive and dated')
    root.mkdir(parents=False, exist_ok=False)
    assets, metadata, content = {}, {}, {}
    try:
        for tag, filename, url, baseline_hash, baseline_updated in SOURCES:
            response = client.get(
                f'https://api.github.com/repos/nflverse/nflverse-data/releases/tags/{tag}',
                headers={'Accept': 'application/vnd.github+json', 'Cache-Control': 'no-cache'})
            if response.is_redirect:
                raise ValueError('Release metadata redirect refused')
            response.raise_for_status()
            raw = response.content
            if not 0 < len(raw) <= MAX_METADATA_BYTES:
                raise ValueError('Release metadata unbounded')
            entry = validate_asset(json.loads(raw), tag, filename, url,
                                   baseline_hash, baseline_updated, now)
            body = download_asset(client, url, entry['sha256'])
            if len(body) != entry['size']:
                raise ValueError('Release asset size differs')
            assets[tag] = entry
            metadata[tag] = raw
            content[filename] = body
    except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError) as exc:
        receipt = dict(protocol=VERSION, status='unavailable',
                       observed_at=now.isoformat(), reason=type(exc).__name__,
                       assets={}, release_metadata_sha256={})
    else:
        receipt = dict(protocol=VERSION, status='observed',
                       observed_at=now.isoformat(), assets=assets,
                       release_metadata_sha256={
                           tag: hashlib.sha256(raw).hexdigest()
                           for tag, raw in metadata.items()})
        for tag, raw in metadata.items():
            with (root/f'{tag}-release.json').open('xb') as stream:
                stream.write(raw)
        for filename, raw in content.items():
            with (root/filename).open('xb') as stream:
                stream.write(raw)
    with (root/'receipt.json').open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2, allow_nan=False)
    return receipt


def verify(root: Path, *, before: datetime) -> str:
    if root.is_symlink() or not root.is_dir() or before.utcoffset() is None:
        raise ValueError('Context source directory unavailable')
    path = root/'receipt.json'
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 100_000:
        raise ValueError('Context receipt missing or unbounded')
    raw = path.read_bytes()
    receipt = json.loads(raw)
    observed = clock(receipt['observed_at'])
    if receipt.get('protocol') != VERSION or not observed <= before:
        raise ValueError('Context source chronology changed')
    expected = {row[0] for row in SOURCES}
    if receipt.get('status') == 'unavailable':
        if (type(receipt.get('reason')) is not str or receipt.get('assets') != {}
                or receipt.get('release_metadata_sha256') != {}
                or set(root.iterdir()) != {path}):
            raise ValueError('Unavailable context receipt changed')
    elif receipt.get('status') == 'observed':
        if (set(receipt.get('assets', {})) != expected
                or set(receipt.get('release_metadata_sha256', {})) != expected):
            raise ValueError('Context source set changed')
        expected_files = {path}
        for tag, filename, url, baseline_hash, baseline_updated in SOURCES:
            meta, asset = root/f'{tag}-release.json', root/filename
            expected_files.update((meta, asset))
            if (meta.is_symlink() or asset.is_symlink() or not meta.is_file()
                    or not asset.is_file() or not 0 < meta.stat().st_size <= MAX_METADATA_BYTES
                    or not 0 < asset.stat().st_size <= 2_000_000):
                raise ValueError('Context asset missing or unbounded')
            meta_raw = meta.read_bytes()
            if hashlib.sha256(meta_raw).hexdigest() != receipt['release_metadata_sha256'][tag]:
                raise ValueError('Context release metadata changed')
            entry = validate_asset(json.loads(meta_raw), tag, filename, url,
                                   baseline_hash, baseline_updated, observed)
            body = asset.read_bytes()
            if (entry != receipt['assets'][tag] or len(body) != entry['size']
                    or hashlib.sha256(body).hexdigest() != entry['sha256']):
                raise ValueError('Context asset bytes changed')
        if set(root.iterdir()) != expected_files:
            raise ValueError('Unexpected context source file')
    else:
        raise ValueError('Context source status changed')
    return hashlib.sha256(raw).hexdigest()
