"""A team-present partial feed must not become snap-backed receiving zeros."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib

import polars as pl
import pytest

from sportsbet.quant import kalshi_stat_only_source_receiving as receiving
from sportsbet.quant import kalshi_stat_only_source_week as freshness


def rows(team='A', week=3, season=2026):
    common = dict(team=team, week=week, season=season, season_type='REG')
    return [dict(common, player_id='QB', completions=2, receptions=0,
                 passing_yards=30, receiving_yards=0),
            dict(common, player_id='WR', completions=0, receptions=2,
                 passing_yards=0, receiving_yards=25),
            dict(common, player_id='LATERAL', completions=0, receptions=0,
                 passing_yards=0, receiving_yards=5)]


def test_team_presence_gate_accepts_a_dropped_receiver_but_accounting_refuses_it():
    teams = [f'T{i:02d}' for i in range(32)]
    schedule = [dict(season=2026, game_type='REG', week=3, gameday='2026-09-28',
                     home_team=teams[i*2], away_team=teams[i*2+1]) for i in range(16)]
    stats = [row for team in teams for row in rows(team)]
    snaps = [dict(season=2026, week=3, game_type='REG', team=team) for team in teams]
    assert receiving.verify(stats)['regular_season_team_games'] == 32
    partial = [row for row in stats if not (row['team'] == teams[0] and row['player_id'] == 'WR')]
    assert freshness.verify(schedule, partial, snaps,
        observed_at=datetime(2026, 10, 4, tzinfo=timezone.utc))['stats_teams'] == 32
    with pytest.raises(ValueError, match='does not reconcile'):
        receiving.verify(partial)


def test_missing_zero_reception_lateral_is_detected_by_yards():
    assert receiving.verify(rows())['counts_reconciled']
    with pytest.raises(ValueError, match='does not reconcile'):
        receiving.verify(rows()[:-1])


def test_trick_passers_and_negative_yards_are_valid():
    stats = rows()
    stats[1].update(completions=1, passing_yards=-2)
    stats.append(dict(stats[1], player_id='RB', completions=0, passing_yards=0,
                      receptions=1, receiving_yards=-2))
    report = receiving.verify(stats)
    assert report['yards_reconciled'] and not report['proves_every_player_present']


@pytest.mark.parametrize('field', receiving.FIELDS)
@pytest.mark.parametrize('value', [None, True, .5, float('nan'), float('inf'), '0'])
def test_missing_or_malformed_statistics_never_become_zero(field, value):
    stats = rows()
    stats[0][field] = value
    with pytest.raises(ValueError, match='statistics'):
        receiving.verify(stats)


def test_negative_counts_and_duplicate_zero_rows_are_rejected():
    stats = rows()
    stats[0]['completions'] = -1
    with pytest.raises(ValueError, match='statistics'):
        receiving.verify(stats)


def test_anonymous_zero_placeholders_are_not_player_or_team_coverage():
    zero = dict(rows()[0], player_id=None, completions=0, passing_yards=0)
    report = receiving.verify([*rows(), zero])
    assert report['regular_season_player_rows'] == 3
    assert report['regular_season_source_rows'] == 4
    assert report['anonymous_zero_rows_excluded'] == 1
    with pytest.raises(ValueError, match='no regular-season team games'):
        receiving.verify([zero])
    with pytest.raises(ValueError, match='identity invalid'):
        receiving.verify([dict(zero, receptions=1)])
    with pytest.raises(ValueError, match='duplicate anonymous'):
        receiving.verify([*rows(), zero, zero])
    stats = rows()
    zero = dict(stats[0], player_id='ZERO', completions=0, passing_yards=0)
    stats += [zero, deepcopy(zero)]
    with pytest.raises(ValueError, match='duplicate'):
        receiving.verify(stats)


def test_verified_bytes_are_parsed_and_changed_assets_refused(tmp_path, monkeypatch):
    observed = datetime(2026, 10, 8, 17, tzinfo=timezone.utc)
    manifest = tmp_path/'source-manifest.json'
    manifest.write_text('{}', encoding='utf-8')
    assets = {}
    for year in receiving.sources.YEARS:
        path = tmp_path/receiving.sources.filename('stats', year)
        pl.DataFrame(rows(season=year)).write_parquet(path)
        assets[f'stats_{year}'] = dict(size=path.stat().st_size,
                                      sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(receiving.sources, 'validate_manifest', lambda *args: assets)
    report = receiving.verify_files(tmp_path, observed_at=observed)
    assert report['regular_season_team_games'] == 3
    assert report['regular_season_player_rows'] == 9
    assert report['observed_at'] == observed.isoformat()
    assert len(report['implementation_sha256']) == 64
    last = tmp_path/receiving.sources.filename('stats', receiving.sources.YEARS[-1])
    last.write_bytes(last.read_bytes()+b' ')
    with pytest.raises(ValueError, match='hash or size'):
        receiving.verify_files(tmp_path, observed_at=observed)
    last.unlink()
    last.mkdir()
    with pytest.raises(ValueError, match='missing, linked or unbounded'):
        receiving.verify_files(tmp_path, observed_at=observed)
