"""A partial current-week archive cannot look like complete player context."""
from datetime import datetime, timezone

import pytest

from sportsbet.quant.kalshi_stat_only_source_week import verify


def fixtures():
    teams = [f'T{i:02d}' for i in range(32)]
    schedule = []
    for week, day in ((3, '2026-09-28'), (4, '2026-10-05')):
        for index in range(16):
            schedule.append({'season': 2026, 'game_type': 'REG', 'week': week,
                             'gameday': day,
                             'home_team': teams[index * 2],
                             'away_team': teams[index * 2 + 1]})
    stats = [{'season': 2026, 'week': 3, 'season_type': 'REG', 'team': team}
             for team in teams]
    snaps = [{'season': 2026, 'week': 3, 'game_type': 'REG', 'team': team}
             for team in teams]
    return schedule, stats, snaps, teams


def test_latest_whole_week_requires_all_team_stats_and_snaps():
    schedule, stats, snaps, teams = fixtures()
    first = datetime(2026, 10, 4, 16, tzinfo=timezone.utc)
    later = datetime(2026, 10, 8, 17, tzinfo=timezone.utc)
    assert verify(schedule, stats, snaps, observed_at=first)['week'] == 3
    with pytest.raises(ValueError, match='lacks team stats or snaps'):
        verify(schedule, stats, snaps, observed_at=later)
    stats += [{'season': 2026, 'week': 4, 'season_type': 'REG', 'team': team}
              for team in teams]
    snaps += [{'season': 2026, 'week': 4, 'game_type': 'REG', 'team': team}
              for team in teams[:-1]]
    with pytest.raises(ValueError, match='lacks team stats or snaps'):
        verify(schedule, stats, snaps, observed_at=later)
    snaps.append({'season': 2026, 'week': 4, 'game_type': 'REG',
                  'team': teams[-1]})
    assert verify(schedule, stats, snaps, observed_at=later)['week'] == 4


def test_week_without_whole_schedule_does_not_create_false_freshness():
    schedule, stats, snaps, _ = fixtures()
    schedule = [game for game in schedule
                if game['week'] == 3 or game['home_team'] != 'T00']
    with pytest.raises(ValueError, match='lacks team stats or snaps'):
        verify(schedule, stats, snaps,
               observed_at=datetime(2026, 10, 8, 17,
                                    tzinfo=timezone.utc))


def test_missing_new_week_cannot_fall_back_to_ten_day_old_sources():
    schedule, stats, snaps, _ = fixtures()
    schedule = [game for game in schedule if game['week'] == 3]
    with pytest.raises(ValueError, match='too old'):
        verify(schedule, stats, snaps,
               observed_at=datetime(2026, 10, 8, 17,
                                    tzinfo=timezone.utc))
