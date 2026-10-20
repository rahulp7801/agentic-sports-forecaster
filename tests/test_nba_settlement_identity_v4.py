"""Synthetic live v4 settlements; no provider, network or PostgreSQL calls."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime

import pytest

from sportsbet.ingestion.provenance import stat_row_sha256
from sportsbet.ledger import Ledger as FrozenLedger, verified_settlement_evidence as frozen_verified
from sportsbet.live_settlement_ledger import Ledger, VERSION, verified_settlement_evidence
from sportsbet.settlement import settle_final_props
from tests.test_nba_settlement_identity import (
    CAPTURED, OBSERVED, START, canonical, create_stats, payload, raw_state,
    reference, retained_proof, schedule, stat_row,
)


ALIASES = (
    ('GS', 'Golden State Warriors', 'GSW'),
    ('NO', 'New Orleans Pelicans', 'NOP'),
    ('NY', 'New York Knicks', 'NYK'),
    ('SA', 'San Antonio Spurs', 'SAS'),
    ('WSH', 'Washington Wizards', 'WAS'),
)


def case(alias=ALIASES[0], *, side='home', hybrid=False):
    raw, name, team = alias
    opponent = ('UTAH', 'Utah Jazz') if hybrid else ('BOS', 'Boston Celtics')
    other = 'away' if side == 'home' else 'home'
    value = payload()
    value.update({side+'_team': name, other+'_team': opponent[1]})
    slate = schedule(value)
    slate['games'][0].update({side+'_abbr': raw, other+'_abbr': opponent[0]})
    return value, slate, team


def proof_for(value, slate, team, *, version=4, points=21):
    proof = retained_proof(value, version=version, points=points)
    game = slate['games'][0]
    proof.update({key: game[key] for key in (
        'home_abbr', 'away_abbr', 'home_name', 'away_name', 'game_time')})
    proof['stat_row'] = stat_row(team=team, points=points)
    proof['stat_record_sha256'] = stat_row_sha256('nba', proof['stat_row'])
    return proof


def write(ledger, key, proof):
    ledger.settle({key: True}, source='observed_final_stats', source_ref=reference(proof),
        observed_at=datetime.fromisoformat(CAPTURED), actual_values={key: 21},
        evidence={key: proof})


@pytest.mark.parametrize('alias', ALIASES, ids=[alias[0] for alias in ALIASES])
@pytest.mark.parametrize('side', ['home', 'away'])
def test_new_alias_settlement_retains_raw_schedule_and_hashed_canonical_stat(tmp_path, alias, side):
    ledger = Ledger(tmp_path/'audit.sqlite')
    value, slate, team = case(alias, side=side)
    key = ledger.record('scan', value)
    row = create_stats(ledger, team=team)
    before = deepcopy((value, slate))
    assert raw_state(ledger, key) == (None,)*6
    with ledger.connect() as db:
        original_payload = db.execute('SELECT payload FROM predictions WHERE id=?', (key,)).fetchone()[0]
        original_stat = db.execute('SELECT * FROM nba_player_gamelogs').fetchone()

    result = settle_final_props(ledger, 'nba', slate)

    assert result['settled'] == 1 and result['pending'] == 0
    stored = ledger.predictions()[0]
    proof = stored['outcome_evidence']
    assert proof['schedule_identity_version'] == 4
    assert proof[side+'_abbr'] == alias[0] and proof[side+'_name'] == alias[1]
    assert proof['stat_row'] == row and proof['stat_row']['team_abbreviation'] == team
    assert proof['stat_record_sha256'] == stat_row_sha256('nba', row)
    assert proof['stat_source_sha256'] == 'a'*64 and proof['game_time'] == START
    assert proof['stat_observed_at'] == OBSERVED and stored['outcome_observed_at'] == CAPTURED
    assert stored['outcome_ref'] == reference(proof) and stored['captured_at'] == value['captured_at']
    assert verified_settlement_evidence(stored, True, stored['outcome_source'], stored['outcome_ref'],
        stored['outcome_observed_at'], stored['actual_value'], proof)
    assert not frozen_verified(stored, True, stored['outcome_source'], stored['outcome_ref'],
        stored['outcome_observed_at'], stored['actual_value'], proof)
    assert ledger.report()['settled_count'] == 1
    assert ledger.report()['settlement_evidence_protocol'] == VERSION
    frozen = FrozenLedger(tmp_path/'audit.sqlite').report()
    assert frozen['settled_count'] == 0 and frozen['unverified_settlements'] == 1
    with ledger.connect() as db:
        assert db.execute('SELECT payload FROM predictions WHERE id=?', (key,)).fetchone()[0] == original_payload
        assert db.execute('SELECT * FROM nba_player_gamelogs').fetchone() == original_stat
    assert (value, slate) == before


@pytest.mark.parametrize('side', ['home', 'away'])
def test_new_alias_and_utah_hybrid_uses_v4_without_rewriting_either_source_pair(tmp_path, side):
    ledger = Ledger(tmp_path/'audit.sqlite')
    value, slate, team = case(side=side, hybrid=True)
    ledger.record('scan', value)
    create_stats(ledger, team=team)
    before = deepcopy(slate)
    assert settle_final_props(ledger, 'nba', slate)['settled'] == 1
    proof = ledger.predictions()[0]['outcome_evidence']
    assert proof['schedule_identity_version'] == 4
    assert {proof['home_abbr'], proof['away_abbr']} == {'UTAH', 'GS'}
    assert proof['stat_row']['team_abbreviation'] == 'GSW' and slate == before


def test_verified_v4_recheck_and_genuine_stat_correction_keep_the_same_policy(tmp_path):
    ledger = Ledger(tmp_path/'audit.sqlite')
    value, slate, team = case()
    ledger.record('scan', value)
    create_stats(ledger, team=team)
    assert settle_final_props(ledger, 'nba', slate)['settled'] == 1
    assert settle_final_props(ledger, 'nba', slate)['settled'] == 1
    corrected = stat_row(team=team, points=0)
    with ledger.connect() as db:
        db.execute('UPDATE nba_player_gamelogs SET points=?,source_record_sha256=?',
            (0, stat_row_sha256('nba', corrected)))
    assert settle_final_props(ledger, 'nba', slate)['settled'] == 1
    stored = ledger.predictions()[0]
    assert stored['outcome'] is False and stored['actual_value'] == 0
    assert stored['outcome_evidence']['schedule_identity_version'] == 4
    assert stored['outcome_evidence']['home_abbr'] == 'GS'
    assert raw_state(ledger, stored['prediction_id'])[5] == canonical(stored['outcome_evidence'])


@pytest.mark.parametrize('tampered', [False, True])
def test_live_board_verifies_v4_and_rejects_changed_retained_stat(tmp_path, monkeypatch, tampered):
    from sportsbet.picks import build_pick_board
    ledger = Ledger(tmp_path/'audit.sqlite')
    value, slate, team = case()
    value.update(model_version='synthetic-model', model_sample_size=40,
        model_confidence_interval=[.55, .8], model_mean_stat=21, stake_fraction=.01,
        quote_time=value['captured_at'], model_generated_at=value['captured_at'],
        recommendation_policy_version='confidence-floor-v2', accepted=True, gate_reason='accepted')
    ledger.record('scan', value)
    create_stats(ledger, team=team)
    assert settle_final_props(ledger, 'nba', slate)['settled'] == 1
    record = ledger.predictions()[0]
    if tampered:
        record['outcome_evidence']['stat_row']['points'] = 99
    # Isolate final-result grading from separately tested pregame admission.
    monkeypatch.setattr('sportsbet.picks._accepted', lambda *_: True)
    board = build_pick_board([record], 'nba', datetime.fromisoformat(CAPTURED))
    assert board['history'][0]['result_verified'] is (not tampered)
    assert board['history'][0]['result'] == ('pending' if tampered else 'win')
    assert board['history'][0]['actual_value'] == (None if tampered else 21)


@pytest.mark.parametrize('change', [
    'wrong_name', 'unknown_alias', 'wrong_team', 'wrong_player', 'wrong_date',
    'source_provider', 'source_hash', 'record_hash', 'stat_clock', 'settlement_clock',
    'wrong_sport', 'version2', 'version3', 'version_string', 'version_float', 'version_false', 'version_unknown',
])
def test_v4_verifier_rejects_changed_identity_provenance_and_policy_even_with_new_outer_hash(change):
    value, slate, team = case()
    proof = proof_for(value, slate, team)
    observed = CAPTURED
    if change == 'wrong_name': proof['home_name'] = value['home_team'] = 'New York Knicks'
    elif change == 'unknown_alias': proof['home_abbr'] = 'ZZ'
    elif change == 'wrong_team': proof['stat_row']['team_abbreviation'] = 'OTH'
    elif change == 'wrong_player': proof['stat_row']['player_id'] = 8
    elif change == 'wrong_date': proof['stat_row']['game_date'] = '2026-10-17'
    elif change == 'source_provider': proof['stat_provider'] = 'untrusted'
    elif change == 'source_hash': proof['stat_source_sha256'] = 'x'*64
    elif change == 'record_hash': proof['stat_record_sha256'] = '0'*64
    elif change == 'stat_clock': proof['stat_observed_at'] = '2026-10-18T17:00:00+00:00'
    elif change == 'settlement_clock': observed = START
    elif change == 'wrong_sport': value['sport'] = 'nfl'
    elif change == 'version2': proof['schedule_identity_version'] = 2
    elif change == 'version3': proof['schedule_identity_version'] = 3
    elif change == 'version_string': proof['schedule_identity_version'] = '4'
    elif change == 'version_float': proof['schedule_identity_version'] = 4.0
    elif change == 'version_false': proof['schedule_identity_version'] = False
    elif change == 'version_unknown': proof['schedule_identity_version'] = 5
    if change in ('wrong_team', 'wrong_player', 'wrong_date'):
        proof['stat_record_sha256'] = stat_row_sha256('nba', proof['stat_row'])
    assert not verified_settlement_evidence(value, True, 'observed_final_stats', reference(proof),
        observed, 21, proof)


@pytest.mark.parametrize('column, raw', [
    ('outcome', 'null'), ('outcome_source', 'old-source'), ('outcome_ref', 'old-reference'),
    ('outcome_observed_at', 'old-clock'), ('actual_value', 'invalid-number'), ('outcome_evidence', 'null'),
])
def test_first_v4_write_requires_all_six_raw_sql_null_fields(tmp_path, column, raw):
    ledger = Ledger(tmp_path/'audit.sqlite')
    value, slate, team = case()
    key = ledger.record('scan', value)
    with ledger.connect() as db:
        db.execute('UPDATE predictions SET '+column+'=? WHERE id=?', (raw, key))
    before = raw_state(ledger, key)
    with pytest.raises(ValueError, match='cannot replace retained evidence'):
        write(ledger, key, proof_for(value, slate, team))
    assert raw_state(ledger, key) == before


@pytest.mark.parametrize('old_version', [1, 2, 3])
def test_new_v4_writer_cannot_replace_retained_earlier_policy(tmp_path, old_version):
    ledger = Ledger(tmp_path/'audit.sqlite')
    value, slate, team = case(side='away', hybrid=old_version == 3)
    key = ledger.record('scan', value)
    old_team = 'UTA' if old_version == 3 else ('GS' if old_version == 2 else team)
    write(ledger, key, proof_for(value, slate, old_team, version=old_version))
    before = raw_state(ledger, key)
    with pytest.raises(ValueError, match='cannot replace retained evidence'):
        write(ledger, key, proof_for(value, slate, team))
    assert raw_state(ledger, key) == before


@pytest.mark.parametrize('old_version, incoming_version', [(3, 4), (4, 3)])
def test_verified_extended_versions_cannot_migrate_each_other(tmp_path, old_version, incoming_version):
    ledger = Ledger(tmp_path/'audit.sqlite')
    value, slate, _ = case(side='away', hybrid=True)
    key = ledger.record('scan', value)
    write(ledger, key, proof_for(value, slate, 'UTA', version=old_version))
    before = raw_state(ledger, key)
    with pytest.raises(ValueError, match='cannot replace retained evidence'):
        write(ledger, key, proof_for(value, slate, 'UTA', version=incoming_version))
    assert raw_state(ledger, key) == before


@pytest.mark.parametrize('old_version', [3, 4])
@pytest.mark.parametrize('incoming', [1, 2, 'manual'])
def test_legacy_or_manual_writer_cannot_downgrade_verified_extended_result(tmp_path, old_version, incoming):
    ledger = Ledger(tmp_path/'audit.sqlite')
    value, slate, team = case(side='away', hybrid=old_version == 3)
    key = ledger.record('scan', value)
    old_team = 'UTA' if old_version == 3 else team
    write(ledger, key, proof_for(value, slate, old_team, version=old_version))
    before = raw_state(ledger, key)
    if incoming == 'manual':
        with pytest.raises(ValueError, match='cannot replace retained evidence'):
            ledger.settle({key: False}, source='manual')
    else:
        legacy_slate = deepcopy(slate)
        if incoming == 2:
            # Legacy canonical spelling makes this a valid v2 proof independently.
            for game in legacy_slate['games']:
                if game['home_abbr'] == 'UTAH': game['home_abbr'] = 'UTA'
                if game['away_abbr'] == 'GS': game['away_abbr'] = 'GSW'
        proof = proof_for(value, legacy_slate, old_team, version=incoming)
        assert frozen_verified(value, True, 'observed_final_stats', reference(proof), CAPTURED, 21, proof)
        with pytest.raises(ValueError, match='cannot replace retained evidence'):
            write(ledger, key, proof)
    assert raw_state(ledger, key) == before


@pytest.mark.parametrize('incoming_version, concurrent_version', [(4, 1), (1, 4)])
def test_compare_and_set_keeps_concurrent_policy_and_rolls_back_other_batch_updates(
        tmp_path, monkeypatch, incoming_version, concurrent_version):
    ledger = Ledger(tmp_path/'audit.sqlite')
    value, slate, team = case()
    key = ledger.record('raced', value)
    other = ledger.record('other', value | {'line': 19.5})
    incoming = proof_for(value, slate, team, version=incoming_version)
    concurrent_proof = proof_for(value, slate, team, version=concurrent_version)
    original_connect = ledger.connect
    injected = False

    @contextmanager
    def connection():
        nonlocal injected
        with original_connect() as db:
            class Proxy:
                def execute(self, sql, args=()):
                    nonlocal injected
                    cursor = db.execute(sql, args)
                    if 'SELECT outcome,outcome_source,outcome_ref,' in sql and args == (key,) and not injected:
                        prior = cursor.fetchone()
                        injected = True
                        with original_connect() as concurrent:
                            concurrent.execute('''UPDATE predictions SET outcome=?,outcome_source=?,outcome_ref=?,
                                outcome_observed_at=?,actual_value=?,outcome_evidence=? WHERE id=?''',
                                ('true', 'observed_final_stats', reference(concurrent_proof), CAPTURED,
                                    21, canonical(concurrent_proof), key))

                        class Prior:
                            def fetchone(self): return prior
                        return Prior()
                    return cursor

                def executemany(self, *args): return db.executemany(*args)
            yield Proxy()

    monkeypatch.setattr(ledger, 'connect', connection)
    with pytest.raises(ValueError, match='prior state changed'):
        ledger.settle({other: True, key: True}, source='observed_final_stats', source_ref=reference(incoming),
            observed_at=datetime.fromisoformat(CAPTURED), actual_values={other: 21, key: 21},
            evidence={other: incoming, key: incoming})
    assert injected
    assert raw_state(ledger, key) == ('true', 'observed_final_stats', reference(concurrent_proof),
        CAPTURED, 21, canonical(concurrent_proof))
    assert raw_state(ledger, other) == (None,)*6


def test_v4_reader_rejects_naive_settlement_datetime_even_for_an_otherwise_valid_proof():
    value,slate,team=case();proof=proof_for(value,slate,team)
    assert not verified_settlement_evidence(value,True,'observed_final_stats',reference(proof),
        datetime.fromisoformat(CAPTURED).replace(tzinfo=None),21,proof)

