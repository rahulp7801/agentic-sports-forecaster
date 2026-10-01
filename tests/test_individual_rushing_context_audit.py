from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib

import pytest
from tests.test_model_selection_paper import receipt, rows, NOW

from sportsbet.ingestion.provenance import stat_row_sha256
from sportsbet.quant import current_history_replay as replay
from sportsbet.quant import individual_rushing_context_audit as audit


CAPTURE = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)


def fixture():
    rows = []
    for i in range(20):
        season = 2025 if i < 17 else 2026
        week = i+1 if season == 2025 else i-16
        item = dict(player_id='p', season=season, week=week, team='PIT',
            passing_yards=0, rushing_yards=80 if i % 4 == 0 else 40,
            receiving_yards=0, receptions=0, carries=10+i,
            source_provider='nflverse', source_observed_at='2026-09-18T00:00:00+00:00',
            source_sha256='a'*64, supplement_inserted_at=None)
        item['source_record_sha256'] = stat_row_sha256('nfl', item)
        rows.append(item)
    games = [dict(season=r['season'], week=r['week'], home_team='PIT', away_team='CLE',
                  game_date='2026-09-17' if r['season'] == 2026 else '2025-09-01',
                  game_id=f"{r['season']}_{r['week']:02}_CLE_PIT",
                  created_at='2026-09-18T00:00:00+00:00') for r in rows]
    snapshot = dict(observed_at='2026-09-19T00:00:00+00:00', nfl_base=rows,
                    nfl_receiving=[], cfb=[], nfl_games=games, cfb_supplement_receipts=[])
    selection = dict(prop_type='rush_yds', line=73.5, direction='under', probability=None)
    sample, _ = replay.History(snapshot).sample('nfl', 'p', 'rush_yds', CAPTURE.date(), CAPTURE)
    estimate = replay.estimate(sample, 73.5)
    selection['probability'] = 1-estimate['p']
    row = dict(player_id='p', prop_type='rush_yds', direction='under', game_date='2026-09-20',
               captured_at=CAPTURE.isoformat(), history_observed_before=(CAPTURE-timedelta(seconds=1)).isoformat(),
               model_sample_size=estimate['n'], model_mean_stat=estimate['mean'],
               model_probability=selection['probability'], availability=dict(status='observed',
                   roster_confirmed=True, captured_at=(CAPTURE-timedelta(seconds=2)).isoformat(),
                   team='PIT', source_sha256='b'*64, roster_source_sha256='c'*64))
    receipt = dict(recorded_at=(CAPTURE+timedelta(seconds=2)).isoformat())
    return row, selection, receipt, snapshot


def context(row, selection, receipt, snapshot):
    return audit.reconstructed_context(row, selection, receipt, snapshot, replay.History(snapshot))


def test_reconstructed_baseline_has_descriptive_recent_and_season_counts_only():
    args = fixture()
    before = deepcopy(args)
    result = context(*args)
    assert result['available'] and result['baseline_sample_size'] == 20
    assert result['recent_games'] == 10 and result['current_season_games'] == 3
    assert result['original_input_receipt'] is False
    assert result['participation_completeness_verified'] is False
    assert args == before


@pytest.mark.parametrize('fault,reason', [
    ('future_snapshot', 'invalid_source_chronology'),
    ('late_row', 'baseline_not_reproduced'),
    ('altered_baseline', 'baseline_not_reproduced'),
    ('altered_team', 'latest_game_or_team_unverified'),
    ('duplicate', 'duplicate_history_key'),
    ('ambiguous_binding', 'ambiguous_history_binding'),
    ('stale_roster', 'stale_or_future_roster'),
    ('tampered_source', 'invalid_source_row_commitment'),
    ('late_schedule', 'invalid_schedule_chronology'),
    ('wrong_game_id', 'invalid_schedule_chronology'),
    ('duplicate_schedule', 'ambiguous_schedule_binding'),
])
def test_missing_or_changed_as_of_evidence_abstains(fault, reason):
    row, selection, receipt, snapshot = fixture()
    if fault == 'future_snapshot': snapshot['observed_at'] = (CAPTURE+timedelta(seconds=1)).isoformat()
    if fault == 'late_row': snapshot['nfl_base'][0]['source_observed_at'] = (CAPTURE+timedelta(seconds=1)).isoformat()
    if fault == 'altered_baseline': row['model_mean_stat'] += 1
    if fault == 'altered_team': row['availability']['team'] = 'CLE'
    if fault == 'duplicate': snapshot['nfl_base'].append(deepcopy(snapshot['nfl_base'][0]))
    if fault == 'ambiguous_binding':
        snapshot['nfl_base'].append(deepcopy(snapshot['nfl_base'][0]))
        snapshot['nfl_base'][-1]['season'] = 2024
    if fault == 'stale_roster': row['availability']['captured_at'] = (CAPTURE-timedelta(hours=2)).isoformat()
    if fault == 'tampered_source':
        snapshot['nfl_base'][0]['rushing_yards'] += 40
        snapshot['nfl_base'][1]['rushing_yards'] -= 40
    if fault == 'late_schedule': snapshot['nfl_games'][0]['created_at'] = (CAPTURE+timedelta(seconds=1)).isoformat()
    if fault == 'wrong_game_id': snapshot['nfl_games'][0]['game_id'] = 'wrong'
    if fault == 'duplicate_schedule': snapshot['nfl_games'].append(deepcopy(snapshot['nfl_games'][0]))
    assert context(row, selection, receipt, snapshot) == {'available': False, 'reason': reason}


def test_original_paper_authentication_precedes_rushing_diagnosis():
    snapshot = fixture()[3]
    source = receipt()
    source['payload'] += ' '
    result = audit.audit([source], rows(), snapshot, NOW+timedelta(minutes=1))
    assert result['status'] == 'invalid_source_evidence'
    assert result['source_audit']['invalid_receipts'] == 1
    assert result['selections'] == [] and not result['promote'] and not result['target_verified']