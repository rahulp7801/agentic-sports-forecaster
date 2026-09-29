from copy import deepcopy
from datetime import date, datetime
import json
from unittest.mock import Mock

import pytest

from sportsbet.ingestion.cfb_final_evidence import digest, inspect_bundle
from sportsbet.ingestion.provenance import stat_row_sha256
from sportsbet.quant.cfb_history_completeness import build_report, load_primary, MAX_ROWS
from tests.test_cfb_final_evidence import bundle, change, NOW, EVENT


def primary(**updates):
    row = inspect_bundle(bundle(), now=NOW)[0]['stat_row'] | dict(
        rushing_yards=68, receiving_yards=None, receptions=None,
        source_provider='sportsdataverse_espn', source_player_sha256='a'*64,
        source_schedule_sha256='b'*64, source_observed_at='2026-09-28T02:00:00Z')
    row.update(updates)
    row['source_sha256'] = digest(json.dumps(dict(player=row['source_player_sha256'],
        schedule=row['source_schedule_sha256']), sort_keys=True, separators=(',', ':')))
    row['source_record_sha256'] = stat_row_sha256('cfb', row)
    return row


def report(rows, b=None, **kwargs):
    return build_report(b or bundle(), rows, cutoff='2026-09-29', season_min=2024,
        now=NOW, **kwargs)


def test_gap_changes_sample_without_mutating_inputs_or_inventing_participation():
    rows = [primary(), primary(game_id=999999990, game_date='2026-09-19',
        receiving_yards=10, receptions=2)]
    before = deepcopy(rows); b = bundle(); before_bundle = deepcopy(b)
    result = report(rows, b)
    assert result['counts'] == {'verified_gap': 1}
    yards, receptions = result['windows']
    assert yards['primary']['n'] == 1 and yards['primary']['mean'] == 10
    assert yards['hypothetical_with_verified_gaps']['n'] == 2
    assert yards['hypothetical_with_verified_gaps']['mean'] == 5
    assert receptions['hypothetical_with_verified_gaps']['mean'] == 1
    assert rows == before and b == before_bundle
    assert result['mode'] == 'read_only' and len(result['limitations']) == 4


def test_latest_window_displaces_older_game_and_keeps_nonmissing_fields():
    result = report([primary(receiving_yards=0), primary(game_id=999999990,
        game_date='2026-09-19', receiving_yards=10, receptions=2)], limit=1)
    assert result['comparisons'][0]['explicit_missing_fields'] == {'receptions': 0}
    yards, catches = result['windows']
    assert yards['primary'] == yards['hypothetical_with_verified_gaps']
    assert catches['added_game_ids'] == [EVENT]
    assert catches['displaced_game_ids'] == ['999999990']


def test_nonzero_explicit_totals_are_audited_too():
    b = bundle()
    change(b, 1, lambda d:d['seasonTypes'][0]['categories'][0]['events'][0]['stats'].__setitem__(slice(2,4), ['1','-2']))
    change(b, 0, lambda d:d['boxscore']['players'][0]['statistics'].append(dict(name='receiving',
        labels=['REC','YDS'], athletes=[dict(athlete=dict(id='201',displayName='Fixture Player'),stats=['1','-2'])])))
    result = report([primary()], b)
    assert result['comparisons'][0]['explicit_missing_fields'] == {'receiving_yards': -2, 'receptions': 1}


@pytest.mark.parametrize('updates', [dict(team_id=77), dict(opponent_id=84), dict(is_home=False),
    dict(week=3), dict(game_date='2026-09-25'), dict(rushing_yards=69),
    dict(receiving_yards=1), dict(receptions=1)])
def test_source_conflict_never_enters_hypothetical_sample(updates):
    result = report([primary(**updates)])
    assert result['counts'] == {'source_conflict': 1}
    for window in result['windows']:
        assert window['primary'] == window['hypothetical_with_verified_gaps']


@pytest.mark.parametrize('field,value', [('source_provider','other'), ('source_sha256','c'*64),
    ('source_record_sha256','d'*64), ('source_player_sha256','e'*64),
    ('source_observed_at','2026-09-30T00:00:00Z'), ('source_observed_at','2026-09-25T00:00:00Z')])
def test_untrusted_primary_prevents_reporting_a_false_clean_sample(field,value):
    row = primary(); row[field] = value
    result = report([row])
    assert result['counts'] == {'primary_provenance_invalid': 1}
    assert result['windows'] == [dict(player_id='201',status='primary_provenance_invalid',invalid_rows=1)]


def test_missing_game_and_missing_final_participation_are_not_synthesized():
    result = report([])
    assert result['counts'] == {'primary_game_missing': 1}
    assert all(w['hypothetical_with_verified_gaps']['n'] == 0 for w in result['windows'])
    b = bundle(); change(b,0,lambda d:d['boxscore']['players'][0].update(statistics=[]))
    result = report([primary()], b)
    assert result['counts'] == {'source_unavailable': 1}


def test_database_types_and_name_changes_preserve_exact_identity():
    row = primary(player_name='Different historical label')
    row.update(game_id=str(row['game_id']), game_date=date.fromisoformat(row['game_date']),
        source_observed_at=datetime.fromisoformat(row['source_observed_at']))
    result = report([row])
    assert result['counts'] == {'verified_gap': 1}
    assert result['comparisons'][0]['player_label_differs'] is True


def test_complete_record_stays_complete():
    result = report([primary(receiving_yards=0,receptions=0)])
    assert result['counts'] == {'complete': 1}
    assert all(w['primary'] == w['hypothetical_with_verified_gaps'] for w in result['windows'])


def test_exclusive_utc_date_and_scope_reject_leakage():
    result = build_report(bundle(), [], cutoff='2026-09-26', season_min=2024, now=NOW)
    assert result['counts'] == {'outside_scope': 1}
    with pytest.raises(ValueError, match='outside requested scope'):
        build_report(bundle(), [primary()], cutoff='2026-09-26', season_min=2024, now=NOW)
    with pytest.raises(ValueError, match='Duplicate primary'):
        report([primary(),primary()])
    with pytest.raises(ValueError, match='scope'):
        report([primary()], limit=41)


def test_read_only_query_binds_scope_and_fails_on_truncation():
    db = Mock(); db.execute.return_value.fetchall.return_value = []
    assert load_primary(db, inspect_bundle(bundle(),now=NOW),cutoff='2026-09-29',season_min=2024) == []
    sql, args = db.execute.call_args.args
    assert sql.startswith('SELECT ') and 'public.cfb_player_gamelogs' in sql
    assert args == ([201],2024,date(2026,9,29),MAX_ROWS+1)
    assert '201' not in sql and '2026-09-29' not in sql
    db.execute.return_value.fetchall.return_value = [()] * (MAX_ROWS+1)
    with pytest.raises(ValueError,match='bound'):
        load_primary(db,inspect_bundle(bundle(),now=NOW),cutoff='2026-09-29',season_min=2024)


def test_unreviewed_missing_categories_remain_visible_and_unknown():
    result = report([primary(), primary(game_id=999999990,game_date='2026-09-19')])
    for window in result['windows']:
        assert window['scoped_primary_games'] == 2
        assert window['remaining_unverified_null_game_ids'] == ['999999990']
        assert window['hypothetical_with_verified_gaps']['n'] == 1
