import json
from copy import deepcopy
from unittest.mock import Mock

import pytest

from sportsbet.ingestion.nfl_final_evidence import inspect_bundle, digest
from sportsbet.ingestion.provenance import stat_row_sha256
from sportsbet.quant.nfl_history_supplements import plan_supplements, apply_bundle, canonical
from tests.test_nfl_final_evidence import bundle, change, NOW


def game():
    return dict(game_id='2026_02_JAX_DEN', season=2026, week=2, game_date='2026-09-20', home_team='DEN', away_team='JAX')


def primary(**changes):
    row = inspect_bundle(bundle(), now=NOW)[0]['stat_row'] | changes
    return row | dict(source_provider='nflverse', source_sha256='a'*64,
        source_record_sha256=stat_row_sha256('nfl', row), source_observed_at=NOW.isoformat())


def test_explicit_missing_row_retains_unknown_other_stats_and_replays():
    b = bundle(); original = deepcopy(b); raw = json.dumps(b)
    plan = plan_supplements(raw, [], [game()], now=NOW); item, = plan['updates']
    assert b == original
    assert item['stat_row']['receptions'] == item['stat_row']['receiving_yards'] == 0
    assert item['stat_row']['rushing_yards'] is item['stat_row']['passing_yards'] is None
    assert item['stat_record_sha256'] == stat_row_sha256('nfl', item['stat_row'])
    assert item['source_sha256'] == digest(canonical(item['manifest']))
    assert item['bundle_sha256'] == digest(raw)
    replay = plan_supplements(raw, [], [game()], [item], now=NOW)
    assert replay['updates'] == [] and replay['retained'] == 1


def test_primary_ingestion_arrival_is_not_overwritten():
    raw = json.dumps(bundle()); row = primary(rushing_yards=4); before = deepcopy(row)
    result = plan_supplements(raw, [row], [game()], now=NOW)
    assert result['updates'] == [] and result['complete'] == 1 and row == before
    prior = plan_supplements(raw, [], [game()], now=NOW)['updates']
    assert plan_supplements(raw, [row], [game()], prior, now=NOW)['retained'] == 1


@pytest.mark.parametrize('changes', [dict(team='JAX'), dict(receptions=1), dict(receiving_yards=1), dict(receptions=None)])
def test_conflicting_primary_fails(changes):
    with pytest.raises(ValueError, match='conflicts'):
        plan_supplements(json.dumps(bundle()), [primary(**changes)], [game()], now=NOW)


@pytest.mark.parametrize('field,value', [('source_record_sha256','0'*64), ('source_sha256','broken'),
    ('source_provider','unknown'), ('source_observed_at','2026-09-24T00:00:00Z'),
    ('source_observed_at','2026-09-19T00:00:00Z')])
def test_uncommitted_primary_is_not_treated_as_complete(field, value):
    row = primary(); row[field] = value
    with pytest.raises(ValueError): plan_supplements(json.dumps(bundle()), [row], [game()], now=NOW)


@pytest.mark.parametrize('games', [[], [game() | dict(game_date='2026-09-21')],
    [game() | dict(home_team='JAX',away_team='DEN')], [game(), game()]])
def test_exact_unique_game_required(games):
    with pytest.raises(ValueError): plan_supplements(json.dumps(bundle()), [], games, now=NOW)


def test_dnp_cannot_create_zero_row():
    b = bundle(); change(b, 1, lambda d:d['entries'][0].update(didNotPlay=True))
    with pytest.raises(ValueError, match='explicit final'):
        plan_supplements(json.dumps(b), [], [game()], now=NOW)


def test_existing_supplement_conflict_requires_review():
    raw = json.dumps(bundle()); prior = plan_supplements(raw, [], [game()], now=NOW)['updates']
    prior[0]['source_sha256'] = 'f'*64
    with pytest.raises(ValueError, match='Existing supplement differs'):
        plan_supplements(raw, [], [game()], prior, now=NOW)


def test_identity_receipt_participates_in_availability_cutoff():
    from datetime import timedelta
    b = bundle(); later = NOW + timedelta(hours=1); b['identity']['retrieved_at'] = later.isoformat()
    item, = plan_supplements(json.dumps(b), [], [game()], now=later)['updates']
    assert item['observed_at'] == later.isoformat()


def test_unreviewed_application_cannot_touch_database():
    db = Mock()
    with pytest.raises(ValueError, match='Positive reviewed count'):
        apply_bundle(db, json.dumps(bundle()), expected_count=0, expected_plan_sha256='x', now=NOW)
    db.execute.assert_not_called()
