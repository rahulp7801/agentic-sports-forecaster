"""Require complete recent NFL team coverage before a prospective paper pair.

The public release timestamp alone cannot show that all teams' latest games
made it into player stats and offensive snaps. Schedule dates determine the
latest whole regular-season week with a two-day publication allowance.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
from pathlib import Path

import polars as pl

from sportsbet.quant import kalshi_role_shadow as role
from sportsbet.quant import kalshi_role_shadow_v2 as source_role

VERSION = 'kalshi-nfl-stat-only-complete-source-week-v1'
PUBLICATION_ALLOWANCE_DAYS = 2
MAX_COMPLETED_WEEK_AGE_DAYS = 7


def verify(schedule_rows: list[dict], stats_rows: list[dict],
           snaps_rows: list[dict], *, observed_at: datetime) -> dict:
    if observed_at.utcoffset() is None:
        raise ValueError('Current-week source check requires aware time')
    day = observed_at.astimezone(timezone.utc).date()
    season = day.year if day.month >= 9 else day.year - 1
    cutoff = day - timedelta(days=PUBLICATION_ALLOWANCE_DAYS)
    weeks: dict[int, list[dict]] = defaultdict(list)
    for game in schedule_rows:
        if game['season'] == season and game['game_type'] == 'REG':
            weeks[int(game['week'])].append(game)
    eligible = [week for week, games in weeks.items()
                if len(games) >= 13 and all(
                    date.fromisoformat(game['gameday']) <= cutoff for game in games)]
    if not eligible:
        raise ValueError('No complete recent NFL schedule week available')
    week = max(eligible)
    games = weeks[week]
    last_game_day = max(date.fromisoformat(game['gameday']) for game in games)
    age = (day - last_game_day).days
    if age > MAX_COMPLETED_WEEK_AGE_DAYS:
        raise ValueError('Latest complete NFL source week is too old')
    expected = [role.team(game[key]) for game in games
                for key in ('home_team', 'away_team')]
    if len(expected) != len(set(expected)):
        raise ValueError('Latest complete NFL schedule week has duplicate teams')

    def teams(rows: list[dict], type_key: str) -> set[str]:
        return {role.team(row['team']) for row in rows
                if row['season'] == season and row['week'] == week
                and row[type_key] == 'REG'}

    stats = teams(stats_rows, 'season_type')
    snaps = teams(snaps_rows, 'game_type')
    if stats != set(expected) or snaps != set(expected):
        raise ValueError('Latest complete NFL week lacks team stats or snaps')
    return {'protocol': VERSION, 'season': season, 'week': week,
            'week_last_game_day': last_game_day.isoformat(),
            'completed_week_age_days': age,
            'schedule_games': len(games), 'expected_teams': len(expected),
            'stats_teams': len(stats), 'snaps_teams': len(snaps),
            'publication_allowance_days': PUBLICATION_ALLOWANCE_DAYS,
            'max_completed_week_age_days': MAX_COMPLETED_WEEK_AGE_DAYS}


def verify_files(source_dir: Path, schedule: Path, *, observed_at: datetime) -> dict:
    if (observed_at.utcoffset() is None
            or source_dir.is_symlink() or not source_dir.is_dir()
            or schedule.is_symlink() or not schedule.is_file()
            or not 0 < schedule.stat().st_size <= 1_000_000):
        raise ValueError('Current-week source or schedule missing or unbounded')
    day = observed_at.astimezone(timezone.utc).date()
    season = day.year if day.month >= 9 else day.year - 1
    stats_path = source_dir / source_role.filename('stats', season)
    snaps_path = source_dir / source_role.filename('snaps', season)
    for path in (stats_path, snaps_path):
        if (path.is_symlink() or not path.is_file()
                or not 0 < path.stat().st_size <= role.MAX_SOURCE_BYTES):
            raise ValueError('Current-week source missing or unbounded')
    schedule_rows = pl.read_parquet(schedule, columns=[
        'season', 'game_type', 'week', 'gameday', 'home_team', 'away_team']).to_dicts()
    stats_rows = pl.read_parquet(stats_path, columns=[
        'season', 'week', 'season_type', 'team']).to_dicts()
    snaps_rows = pl.read_parquet(snaps_path, columns=[
        'season', 'week', 'game_type', 'team']).to_dicts()
    report = verify(schedule_rows, stats_rows, snaps_rows, observed_at=observed_at)
    report.update(observed_at=observed_at.isoformat(),
                  schedule_sha256=hashlib.sha256(schedule.read_bytes()).hexdigest(),
                  stats_sha256=hashlib.sha256(stats_path.read_bytes()).hexdigest(),
                  snaps_sha256=hashlib.sha256(snaps_path.read_bytes()).hexdigest())
    return report
