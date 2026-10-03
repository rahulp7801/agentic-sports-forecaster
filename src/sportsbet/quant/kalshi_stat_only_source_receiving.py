"""Forward source integrity: reconcile player receiving and passing accounting.

This necessary check catches partial receiving feeds, not every missing player.
It supplements the frozen freshness gate without rewriting legacy cohorts.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
from io import BytesIO
import json
from pathlib import Path

import polars as pl

from sportsbet.quant import kalshi_role_shadow as role
from sportsbet.quant import kalshi_role_shadow_v2 as sources

VERSION = 'kalshi-nfl-stat-only-receiving-source-integrity-v1'
FIELDS = ('completions', 'receptions', 'passing_yards', 'receiving_yards')


def integer(value, *, nonnegative: bool) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError('Receiving source has missing or invalid numeric statistics')
    try:
        number = Decimal(str(value))
        if (not number.is_finite() or number != number.to_integral_value()
                or (nonnegative and number < 0)):
            raise ValueError('Receiving source has invalid integer statistics')
        return int(number)
    except InvalidOperation as exc:
        raise ValueError('Receiving source has invalid integer statistics') from exc


def verify(stats_rows: list[dict]) -> dict:
    totals = defaultdict(lambda: [0, 0, 0, 0])
    seen, represented, anonymous = set(), set(), set()
    row_count = 0
    for row in stats_rows:
        if row['season_type'] != 'REG':
            continue
        season = integer(row['season'], nonnegative=True)
        week = integer(row['week'], nonnegative=True)
        player, team = row.get('player_id'), row.get('team')
        if (not isinstance(team, str) or not team.strip() or not 1 <= week <= 18):
            raise ValueError('Receiving source player/team/week identity invalid')
        group = (season, week, role.team(team))
        represented.add(group)
        numbers = [integer(row.get(field), nonnegative=index < 2)
                   for index, field in enumerate(FIELDS)]
        # nflverse includes anonymous zero-stat placeholders. They contribute
        # no player evidence and cannot establish a team's row coverage.
        if player is None and not any(numbers):
            if group in anonymous:
                raise ValueError('Receiving source has duplicate anonymous zero rows')
            anonymous.add(group)
            continue
        if not isinstance(player, str) or not player.strip():
            raise ValueError('Receiving source player/team/week identity invalid')
        identity = (*group, player)
        if identity in seen:
            raise ValueError('Receiving source has duplicate player/team/game rows')
        seen.add(identity)
        row_count += 1
        for index, number in enumerate(numbers):
            totals[group][index] += number
    if not totals or set(totals) != represented:
        raise ValueError('Receiving source has no regular-season team games')
    if any(counts[0] != counts[1] or counts[2] != counts[3] for counts in totals.values()):
        raise ValueError('Receiving source passing/receiving accounting does not reconcile')
    return dict(protocol=VERSION, regular_season_player_rows=row_count,
                regular_season_source_rows=row_count+len(anonymous),
                anonymous_zero_rows_excluded=len(anonymous),
                regular_season_team_games=len(totals), counts_reconciled=True,
                yards_reconciled=True, proves_every_player_present=False)


def read(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise ValueError('Receiving source missing, linked or unbounded')
    with path.open('rb') as stream:
        raw = stream.read(limit+1)
    if not 0 < len(raw) <= limit:
        raise ValueError('Receiving source changed size during read')
    return raw


def verify_files(source_dir: Path, *, observed_at: datetime) -> dict:
    if (observed_at.utcoffset() is None or source_dir.is_symlink() or not source_dir.is_dir()):
        raise ValueError('Receiving source directory or clock invalid')
    manifest_raw = read(source_dir/'source-manifest.json', 2_000_000)
    assets = sources.validate_manifest(json.loads(manifest_raw), observed_at)
    rows, hashes = [], {}
    for year in sources.YEARS:
        name = sources.filename('stats', year)
        raw = read(source_dir/name, role.MAX_SOURCE_BYTES)
        hashed = hashlib.sha256(raw).hexdigest()
        if hashed != assets[f'stats_{year}']['sha256'] or len(raw) != assets[f'stats_{year}']['size']:
            raise ValueError('Receiving source asset hash or size changed')
        # Parse the same bytes that were authenticated, not a second path read.
        selected = pl.read_parquet(BytesIO(raw), columns=[
            'season', 'week', 'season_type', 'team', 'player_id', *FIELDS]).to_dicts()
        if any(row['season'] != year for row in selected):
            raise ValueError('Receiving source asset season changed')
        rows.extend(selected)
        hashes[name] = hashed
    report = verify(rows)
    report.update(observed_at=observed_at.isoformat(), stats_sha256=hashes,
        source_manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
        implementation_sha256=hashlib.sha256(
            Path(__file__).read_bytes().replace(b'\r\n', b'\n')).hexdigest())
    return report
