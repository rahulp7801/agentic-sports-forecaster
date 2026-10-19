"""Synthetic SQLite-only Utah settlements; retained source proofs stay immutable."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

import pytest

from sportsbet.ingestion.provenance import stat_row_sha256
from sportsbet.ledger import Ledger as FrozenLedger, verified_settlement_evidence as frozen_verified
from sportsbet.live_settlement_ledger import Ledger, VERSION, verified_settlement_evidence
from sportsbet.schedules import scheduled_stat_teams
from sportsbet.settlement import settle_final_props


START='2026-10-18T18:00:00+00:00'
OBSERVED='2026-10-19T00:00:00+00:00'
CAPTURED='2026-10-19T01:00:00+00:00'
STATE_COLUMNS='outcome,outcome_source,outcome_ref,outcome_observed_at,actual_value,outcome_evidence'


def payload(*, side='home', line=20.5):
    home,away=('Utah Jazz','Boston Celtics') if side=='home' else ('Boston Celtics','Utah Jazz')
    return dict(game_id='synthetic-odds-event',player='Synthetic Player',player_id='7',sport='nba',
        game_date='2026-10-18',home_team=home,away_team=away,prop_type='points',direction='over',
        line=line,sportsbook='synthetic-book',american_odds=100,model_probability=.6,
        captured_at='2026-10-18T15:00:00+00:00',game_start_time=START)


def schedule(value):
    home='UTAH' if value['home_team']=='Utah Jazz' else 'BOS'
    away='UTAH' if value['away_team']=='Utah Jazz' else 'BOS'
    return dict(status='complete',captured_at=CAPTURED,games=[dict(provider_event_id='401234567',
        date=value['game_date'],home_name=value['home_team'],away_name=value['away_team'],
        home_abbr=home,away_abbr=away,completed=True,game_time=START)])


def stat_row(*, team='UTA', points=21):
    return dict(player_id=7,game_id='0022600001',game_date='2026-10-18',
        team_abbreviation=team,points=points,rebounds=5,assists=4)


def create_stats(ledger, *, team='UTA', points=21):
    row=stat_row(team=team,points=points)
    with ledger.connect() as db:
        db.execute('''CREATE TABLE nba_player_gamelogs (player_id INTEGER,game_id TEXT,
            game_date TEXT,team_abbreviation TEXT,points INTEGER,rebounds INTEGER,assists INTEGER,
            source_provider TEXT,source_sha256 TEXT,source_record_sha256 TEXT,source_observed_at TEXT)''')
        db.execute('INSERT INTO nba_player_gamelogs VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (*row.values(),'nba','a'*64,stat_row_sha256('nba',row),OBSERVED))
    return row


def canonical(proof):
    return json.dumps(proof,sort_keys=True,separators=(',',':'),allow_nan=False)


def reference(proof):
    return 'espn_schedule+nba:401234567:sha256:'+hashlib.sha256(canonical(proof).encode()).hexdigest()


def retained_proof(value, *, version=1, points=21):
    game=schedule(value)['games'][0];row=stat_row(points=points)
    proof=dict(provider_event_id=game['provider_event_id'],date=value['game_date'],
        home_abbr=game['home_abbr'],away_abbr=game['away_abbr'],home_name=game['home_name'],
        away_name=game['away_name'],completed=True,game_time=START,player_id='7',prop_type='points',
        actual_value=str(points),stat_provider='nba',stat_source_sha256='a'*64,
        stat_record_sha256=stat_row_sha256('nba',row),stat_observed_at=OBSERVED,stat_row=row)
    if version is not None:
        proof['schedule_identity_version']=version
    return proof


def raw_state(ledger, key):
    with ledger.connect() as db:
        return db.execute('SELECT '+STATE_COLUMNS+' FROM predictions WHERE id=?',(key,)).fetchone()


@pytest.mark.parametrize('side',['home','away'])
def test_new_utah_settlement_preserves_raw_source_and_canonical_stat_identity(tmp_path,side):
    ledger=Ledger(tmp_path/'audit.sqlite');value=payload(side=side);key=ledger.record('scan',value)
    row=create_stats(ledger);slate=schedule(value);before=deepcopy((value,slate))
    with ledger.connect() as db:
        original_payload=db.execute('SELECT payload FROM predictions WHERE id=?',(key,)).fetchone()[0]
        original_stat=db.execute('SELECT * FROM nba_player_gamelogs').fetchone()

    result=settle_final_props(ledger,'nba',slate)

    assert result['settled']==1 and result['pending']==0
    stored=ledger.predictions()[0];proof=stored['outcome_evidence']
    assert stored['outcome'] is True and proof['schedule_identity_version']==3
    assert proof[side+'_abbr']=='UTAH' and proof[side+'_name']=='Utah Jazz'
    assert proof['stat_row']==row and proof['stat_row']['team_abbreviation']=='UTA'
    assert proof['stat_record_sha256']==stat_row_sha256('nba',row)
    assert proof['stat_source_sha256']=='a'*64 and proof['game_time']==START
    assert proof['stat_observed_at']==OBSERVED and stored['outcome_observed_at']==CAPTURED
    assert stored['captured_at']==value['captured_at'] and (value,slate)==before
    assert verified_settlement_evidence(stored,True,stored['outcome_source'],stored['outcome_ref'],
        stored['outcome_observed_at'],stored['actual_value'],proof)
    assert not frozen_verified(stored,True,stored['outcome_source'],stored['outcome_ref'],
        stored['outcome_observed_at'],stored['actual_value'],proof)
    assert ledger.report()['settled_count']==1
    assert ledger.report()['settlement_evidence_protocol']==VERSION
    frozen_report=FrozenLedger(tmp_path/'audit.sqlite').report()
    assert frozen_report['settled_count']==0 and frozen_report['unverified_settlements']==1
    with ledger.connect() as db:
        assert db.execute('SELECT payload FROM predictions WHERE id=?',(key,)).fetchone()[0]==original_payload
        assert db.execute('SELECT * FROM nba_player_gamelogs').fetchone()==original_stat


def test_live_ledger_keeps_nba_source_time_admission_guard(tmp_path):
    from sportsbet.nba_source_asof import NBA_MODEL_VERSION
    ledger=Ledger(tmp_path/'audit.sqlite')
    with pytest.raises(ValueError,match='NBA source-time prediction requires verified quote evidence'):
        ledger.record('scan',payload()|{'model_version':NBA_MODEL_VERSION})


def test_frozen_ledger_does_not_opt_into_utah_settlement_writes(tmp_path):
    ledger=FrozenLedger(tmp_path/'audit.sqlite');value=payload();key=ledger.record('scan',value)
    create_stats(ledger)
    result=settle_final_props(ledger,'nba',schedule(value))
    assert result['settled']==0 and result['pending']==1
    assert raw_state(ledger,key)==(None,)*6


def test_live_legacy_report_matches_frozen_report_except_explicit_protocol(tmp_path):
    ledger=Ledger(tmp_path/'audit.sqlite');value=payload();key=ledger.record('scan',value)
    proof=retained_proof(value,version=1)
    ledger.settle({key:True},source='observed_final_stats',source_ref=reference(proof),
        observed_at=datetime.fromisoformat(CAPTURED),actual_values={key:21},evidence={key:proof})
    live=ledger.report()
    assert live.pop('settlement_evidence_protocol')==VERSION
    assert live==FrozenLedger(tmp_path/'audit.sqlite').report()


@pytest.mark.parametrize('tampered',[False,True])
def test_live_pick_board_uses_real_v3_result_proof(tmp_path,monkeypatch,tampered):
    from sportsbet.picks import build_pick_board
    ledger=Ledger(tmp_path/'audit.sqlite')
    value=payload()|dict(model_version='synthetic-model',model_sample_size=40,
        model_confidence_interval=[.55,.8],model_mean_stat=21,stake_fraction=.01,
        quote_time='2026-10-18T15:00:00+00:00',model_generated_at='2026-10-18T15:00:00+00:00',
        recommendation_policy_version='confidence-floor-v2',accepted=True,gate_reason='accepted')
    ledger.record('scan',value);create_stats(ledger)
    assert settle_final_props(ledger,'nba',schedule(value))['settled']==1
    record=ledger.predictions()[0]
    if tampered:
        record['outcome_evidence']['stat_row']['points']=99
    # Isolate final-result grading from the separately tested pregame admission.
    monkeypatch.setattr('sportsbet.picks._accepted',lambda *_:True)
    board=build_pick_board([record],'nba',datetime.fromisoformat(CAPTURED))
    assert board['history'][0]['result_verified'] is (not tampered)
    assert board['history'][0]['result']==('pending' if tampered else 'win')
    assert board['history'][0]['actual_value']==(None if tampered else 21)


@pytest.mark.parametrize('change',['wrong_name','unknown_abbreviation','duplicate_canonical','wrong_sport'])
def test_version3_utah_mapping_is_exact_and_sport_specific(change):
    game=schedule(payload())['games'][0];sport='nba'
    if change=='wrong_name': game['home_name']='Philadelphia 76ers'
    if change=='unknown_abbreviation': game['home_abbr']='UTES'
    if change=='duplicate_canonical': game['away_abbr']='UTA'
    if change=='wrong_sport': sport='nfl'
    with pytest.raises(ValueError):
        scheduled_stat_teams(sport,game,identity_version=3)


@pytest.mark.parametrize('version',[None,True,False,'3',3.0,4])
def test_version3_utah_mapping_requires_exact_integer_opt_in(version):
    with pytest.raises(ValueError):
        scheduled_stat_teams('nba',schedule(payload())['games'][0],identity_version=version)


def test_default_and_version2_team_contract_remain_unchanged():
    game=schedule(payload())['games'][0]
    for kwargs in ({},{'identity_version':2}):
        with pytest.raises(ValueError): scheduled_stat_teams('nba',game,**kwargs)
        assert scheduled_stat_teams('nba',dict(home_abbr='GS',away_abbr='BOS'),**kwargs)=={'GS','BOS'}
        assert scheduled_stat_teams('nfl',dict(home_abbr='LAR',away_abbr='WSH'),**kwargs)=={'LA','WAS'}
        assert scheduled_stat_teams('cfb',dict(home_abbr='UTAH',away_abbr='BYU'),**kwargs)=={'UTAH','BYU'}


@pytest.mark.parametrize('sport,prop_type',[('nba','points'),('nfl','pass_yds'),('cfb','pass_yds')])
def test_legacy_candidate_keeps_recovery_writer_triple_contract(sport,prop_type):
    from sportsbet.settlement import _candidate
    value=payload() | {'sport':sport,'prop_type':prop_type}
    game=schedule(value)['games'][0] | {'home_abbr':'UTA'}
    before=deepcopy((value,game))

    matched,day,line=_candidate(value,sport,[game])

    assert matched is game and day==value['game_date'] and line==value['line']
    assert _candidate(value,sport,[]) is None and (value,game)==before


@pytest.mark.parametrize('retained_version',[None,1,3])
def test_legacy_candidate_cannot_opt_raw_utah_into_new_settlement_policy(retained_version):
    from sportsbet.settlement import _candidate
    value=payload()
    if retained_version is not None:
        proof=retained_proof(value,version=retained_version)
        value.update(outcome=True,outcome_source='observed_final_stats',outcome_ref=reference(proof),
            outcome_observed_at=CAPTURED,actual_value=21,outcome_evidence=proof)
    with pytest.raises(ValueError):
        _candidate(value,'nba',schedule(value)['games'])


@pytest.mark.parametrize('team',['OTH','UTAH'])
def test_utah_cannot_settle_from_wrong_or_uncanonical_stat_team(tmp_path,team):
    ledger=Ledger(tmp_path/'audit.sqlite');value=payload();key=ledger.record('scan',value)
    create_stats(ledger,team=team)
    result=settle_final_props(ledger,'nba',schedule(value))
    assert result['settled']==0 and result['pending']==1
    assert result['reasons']=={'stat_not_found_or_ambiguous':1}
    assert raw_state(ledger,key)==(None,)*6


@pytest.mark.parametrize('version',[None,1])
def test_verified_legacy_utah_proof_is_retained_byte_for_byte_on_recheck(tmp_path,version):
    ledger=Ledger(tmp_path/'audit.sqlite');value=payload();key=ledger.record('scan',value)
    create_stats(ledger,points=0);proof=retained_proof(value,version=version)
    ledger.settle({key:True},source='observed_final_stats',source_ref=reference(proof),
        observed_at=datetime.fromisoformat(CAPTURED),actual_values={key:21},evidence={key:proof})
    before=raw_state(ledger,key)

    result=settle_final_props(ledger,'nba',schedule(value))

    assert result['settled']==0 and result['retained_verified']==1 and result['pending']==0
    assert result['retained_recheck_reasons']=={'invalid_prediction_or_evidence':1}
    assert raw_state(ledger,key)==before


@pytest.mark.parametrize('column,raw',[
    ('outcome_evidence','invalid-json'),('outcome_evidence','null'),
    ('outcome','invalid-json'),('actual_value','invalid-number'),
    ('outcome_source','old-source'),('outcome_ref','old-reference'),('outcome_observed_at','old-clock'),
])
def test_nonempty_raw_prior_state_is_not_fresh_after_lossy_decoding(tmp_path,column,raw):
    ledger=Ledger(tmp_path/'audit.sqlite');value=payload();key=ledger.record('scan',value)
    create_stats(ledger)
    with ledger.connect() as db:
        db.execute('UPDATE predictions SET '+column+'=? WHERE id=?',(raw,key))
    before=raw_state(ledger,key)

    result=settle_final_props(ledger,'nba',schedule(value))

    assert result['settled']==0 and result['pending']==1
    assert raw_state(ledger,key)==before


def test_verified_version3_can_recheck_and_record_genuine_stat_correction(tmp_path):
    ledger=Ledger(tmp_path/'audit.sqlite');value=payload();key=ledger.record('scan',value)
    create_stats(ledger);slate=schedule(value)
    assert settle_final_props(ledger,'nba',slate)['settled']==1
    assert settle_final_props(ledger,'nba',slate)['settled']==1
    row=stat_row(points=0)
    with ledger.connect() as db:
        db.execute('UPDATE nba_player_gamelogs SET points=?,source_record_sha256=?',
            (0,stat_row_sha256('nba',row)))

    assert settle_final_props(ledger,'nba',slate)['settled']==1

    stored=ledger.predictions()[0]
    assert stored['outcome'] is False and stored['actual_value']==0
    assert stored['outcome_evidence']['schedule_identity_version']==3
    assert stored['outcome_evidence']['home_abbr']=='UTAH'
    assert raw_state(ledger,key)[5]==canonical(stored['outcome_evidence'])


def test_existing_version3_is_not_downgraded_when_current_source_abbreviation_changes(tmp_path):
    ledger=Ledger(tmp_path/'audit.sqlite');value=payload();key=ledger.record('scan',value)
    create_stats(ledger);slate=schedule(value)
    assert settle_final_props(ledger,'nba',slate)['settled']==1
    before=raw_state(ledger,key)
    slate['games'][0]['home_abbr']='UTA'
    result=settle_final_props(ledger,'nba',slate)
    assert result['settled']==0 and result['retained_verified']==1 and result['pending']==0
    assert raw_state(ledger,key)==before


@pytest.mark.parametrize('change',['version2','wrong_name','wrong_team','wrong_sport','version_string','version_float',
    'wrong_row_player','wrong_row_date'])
def test_tampered_version3_proof_is_rejected_even_with_new_outer_hash(change):
    value=payload();proof=retained_proof(value,version=3)
    if change=='version2': proof['schedule_identity_version']=2
    if change=='wrong_name': proof['home_name']=value['home_team']='Philadelphia 76ers'
    if change=='wrong_team':
        proof['stat_row']['team_abbreviation']='OTH'
        proof['stat_record_sha256']=stat_row_sha256('nba',proof['stat_row'])
    if change=='wrong_row_player':
        proof['stat_row']['player_id']=8
        proof['stat_record_sha256']=stat_row_sha256('nba',proof['stat_row'])
    if change=='wrong_row_date':
        proof['stat_row']['game_date']='2026-10-17'
        proof['stat_record_sha256']=stat_row_sha256('nba',proof['stat_row'])
    if change=='wrong_sport': value['sport']='nfl';value['prop_type']=proof['prop_type']='pass_yds'
    if change=='version_string': proof['schedule_identity_version']='3'
    if change=='version_float': proof['schedule_identity_version']=3.0
    assert not verified_settlement_evidence(value,True,'observed_final_stats',reference(proof),
        CAPTURED,21,proof)


def test_legacy_and_fresh_utah_results_do_not_migrate_or_share_policy(tmp_path,monkeypatch):
    import sportsbet.settlement as settlement
    ledger=Ledger(tmp_path/'audit.sqlite');value=payload();legacy=ledger.record('legacy',value)
    fresh=ledger.record('fresh',payload(line=19.5));create_stats(ledger)
    proof=retained_proof(value,version=1)
    ledger.settle({legacy:True},source='observed_final_stats',source_ref=reference(proof),
        observed_at=datetime.fromisoformat(CAPTURED),actual_values={legacy:21},evidence={legacy:proof})
    before=raw_state(ledger,legacy);calls=[];actual=settlement._actual
    def read(*args):
        calls.append(args[-1]);return actual(*args)
    monkeypatch.setattr(settlement,'_actual',read)

    result=settle_final_props(ledger,'nba',schedule(value))

    assert result['settled']==1 and result['retained_verified']==1 and calls==[3]
    assert raw_state(ledger,legacy)==before
    assert json.loads(raw_state(ledger,fresh)[5])['schedule_identity_version']==3


def test_v3_write_gate_refuses_prior_legacy_state_even_for_direct_writer(tmp_path):
    ledger=Ledger(tmp_path/'audit.sqlite');value=payload();key=ledger.record('scan',value)
    old=retained_proof(value,version=1)
    ledger.settle({key:True},source='observed_final_stats',source_ref=reference(old),
        observed_at=datetime.fromisoformat(CAPTURED),actual_values={key:21},evidence={key:old})
    before=raw_state(ledger,key);new=retained_proof(value,version=3)

    with pytest.raises(ValueError,match='cannot replace retained evidence'):
        ledger.settle({key:True},source='observed_final_stats',source_ref=reference(new),
            observed_at=datetime.fromisoformat(CAPTURED),actual_values={key:21},evidence={key:new})

    assert raw_state(ledger,key)==before


def test_v3_compare_and_set_blocks_concurrent_legacy_result_and_rolls_back_other_updates(tmp_path,monkeypatch):
    ledger=Ledger(tmp_path/'audit.sqlite');value=payload();key=ledger.record('new',value)
    other=ledger.record('other',payload(line=19.5));new=retained_proof(value,version=3)
    old=retained_proof(value,version=1);original_connect=ledger.connect;injected=False
    @contextmanager
    def connection():
        nonlocal injected
        with original_connect() as db:
            class Proxy:
                def execute(self,sql,args=()):
                    nonlocal injected
                    cursor=db.execute(sql,args)
                    if 'SELECT outcome,outcome_source,outcome_ref,' in sql and args==(key,) and not injected:
                        prior=cursor.fetchone();injected=True
                        with original_connect() as concurrent:
                            concurrent.execute('''UPDATE predictions SET outcome=?,outcome_source=?,outcome_ref=?,
                                outcome_observed_at=?,actual_value=?,outcome_evidence=? WHERE id=?''',
                                ('true','observed_final_stats',reference(old),CAPTURED,21,canonical(old),key))
                        class Prior:
                            def fetchone(self): return prior
                        return Prior()
                    return cursor
                def executemany(self,*args): return db.executemany(*args)
            yield Proxy()
    monkeypatch.setattr(ledger,'connect',connection)

    with pytest.raises(ValueError,match='prior state changed'):
        ledger.settle({other:True,key:True},source='observed_final_stats',source_ref=reference(new),
            observed_at=datetime.fromisoformat(CAPTURED),actual_values={other:21,key:21},
            evidence={other:new,key:new})

    assert injected and raw_state(ledger,key)==('true','observed_final_stats',reference(old),
        CAPTURED,21,canonical(old))
    assert raw_state(ledger,other)==(None,)*6
