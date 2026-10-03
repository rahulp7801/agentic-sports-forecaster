from datetime import datetime, timedelta, timezone

import pytest

from sportsbet.picks import build_pick_board


def row(identity: str, captured: datetime, start: datetime, *, probability=.7, outcome=None):
    return dict(prediction_id=identity*64,game_id='game',player='Player',player_id='00-1',sport='nfl',
        game_date=start.date().isoformat(),home_team='Home',away_team='Away',prop_type='pass_yds',
        direction='over',line=250.5,sportsbook='book',american_odds=-110,
        model_probability=probability,push_probability=0,model_sample_size=40,
        model_mean_stat=260.25,
        model_confidence_interval=[.55,.8],captured_at=captured.isoformat(),
        game_start_time=start.isoformat(),quote_time=captured.isoformat(),model_generated_at=captured.isoformat(),
        quote_source_provider='the_odds_api',quote_source_sha256='a'*64,
        quote_source_record_sha256='b'*64,accepted=True,gate_reason='accepted',stake_fraction=.01,
        model_version='empirical-jeffreys-v4',recommendation_policy_version='confidence-floor-v2',
        trade_plan=['one','two','three'],forecast_cutoff=start.date().isoformat(),
        outcome=outcome,outcome_source='observed_final_stats' if outcome is not None else None,
        outcome_ref='proof' if outcome is not None else None,outcome_observed_at=(start+timedelta(hours=4)).isoformat() if outcome is not None else None,
        actual_value=300 if outcome is not None else None,outcome_evidence={'proof':True} if outcome is not None else None)


def test_board_uses_latest_approved_capture_before_fixed_lock(monkeypatch):
    start=datetime(2026,9,20,20,tzinfo=timezone.utc)
    rows=[row('a',start-timedelta(hours=3),start,probability=.65),
          row('b',start-timedelta(minutes=70),start,probability=.7),
          row('c',start-timedelta(minutes=45),start,probability=.8)]
    monkeypatch.setattr('sportsbet.picks.quote_evidence_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.settlement_identity_valid',lambda value:True)
    board=build_pick_board(rows,'nfl',start-timedelta(minutes=30))
    assert len(board['current'])==1
    assert board['current'][0]['prediction_id']=='b'*64
    assert board['current'][0]['board_state']=='locked'
    assert board['current'][0]['lock_at']==(start-timedelta(minutes=60)).isoformat()
    assert board['current'][0]['mean_stat']==260.25
    assert board['selection_policy_version']=='pregame-t60-v1'


def test_board_rejects_invalid_retained_mean(monkeypatch):
    start=datetime(2026,9,20,20,tzinfo=timezone.utc)
    invalid=row('a',start-timedelta(hours=2),start)
    invalid['model_mean_stat']='NaN'
    monkeypatch.setattr('sportsbet.picks.quote_evidence_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.settlement_identity_valid',lambda value:True)
    assert build_pick_board([invalid],'nfl',start-timedelta(hours=1,minutes=30))['current']==[]


def test_board_never_grades_without_reproducible_settlement(monkeypatch):
    start=datetime(2026,9,20,20,tzinfo=timezone.utc)
    rows=[row('a',start-timedelta(minutes=70),start,outcome=True)]
    monkeypatch.setattr('sportsbet.picks.quote_evidence_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.settlement_identity_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.verified_settlement_evidence',lambda *args:False)
    board=build_pick_board(rows,'nfl',start+timedelta(hours=5))
    assert board['history'][0]['result']=='pending'
    assert board['history'][0]['actual_value'] is None
    assert board['summary']=={'current':0,'settled':0,'pending':1,'wins':0,'losses':0,'pushes':0,'verified_win_rate':None}


def test_board_rejects_conflicting_player_game_identity(monkeypatch):
    start=datetime(2026,9,20,20,tzinfo=timezone.utc)
    first=row('a',start-timedelta(hours=3),start)
    second=row('b',start-timedelta(hours=2),start+timedelta(minutes=30))
    monkeypatch.setattr('sportsbet.picks.quote_evidence_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.settlement_identity_valid',lambda value:True)
    board=build_pick_board([first,second],'nfl',start-timedelta(hours=1))
    assert board['current']==[]


def test_board_reports_only_verified_prospective_results(monkeypatch):
    start=datetime(2026,9,20,20,tzinfo=timezone.utc)
    rows=[row('a',start-timedelta(minutes=70),start,outcome=True)]
    monkeypatch.setattr('sportsbet.picks.quote_evidence_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.settlement_identity_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.verified_settlement_evidence',lambda *args:True)
    board=build_pick_board(rows,'nfl',start+timedelta(hours=5))
    assert board['history'][0]['result']=='win' and board['history'][0]['result_verified'] is True
    assert board['summary']['wins']==1 and board['summary']['verified_win_rate']==1


def test_board_totals_describe_only_bounded_public_records(monkeypatch):
    start=datetime(2026,9,20,20,tzinfo=timezone.utc)
    rows=[]
    for index in range(205):
        item=row(f'{index:064x}'[-1],start-timedelta(minutes=70),start,outcome=index % 2 == 0)
        item['prediction_id']=f'{index:064x}'
        item['game_id']=f'game-{index}'
        item['player']=f'Player {index}'
        rows.append(item)
    monkeypatch.setattr('sportsbet.picks.quote_evidence_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.settlement_identity_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.verified_settlement_evidence',lambda *args:True)
    board=build_pick_board(rows,'nfl',start+timedelta(hours=5))
    assert len(board['history'])==200
    assert board['summary']['settled']==200
    assert board['summary']['wins']+board['summary']['losses']==200


@pytest.mark.parametrize('change',[
    {'prediction_id':None}, {'model_sample_size':None}, {'model_sample_size':'40'},
    {'model_sample_size':19}, {'model_sample_size':True}, {'push_probability':-.1},
    {'quote_time':'2026-09-20T17:00:00+00:00'},
    {'model_generated_at':'2026-09-20T19:00:00+00:00'},
    {'trade_plan':['x'*301]}, {'trade_plan':None}, {'model_mean_stat':10001},
])
def test_malformed_retained_pick_cannot_hide_valid_neighbor(monkeypatch,change):
    start=datetime(2026,9,20,20,tzinfo=timezone.utc)
    valid=row('a',start-timedelta(hours=2),start)
    malformed=row('b',start-timedelta(hours=2),start)|change|{'game_id':'other'}
    monkeypatch.setattr('sportsbet.picks.quote_evidence_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.settlement_identity_valid',lambda value:True)
    board=build_pick_board([malformed,valid],'nfl',start-timedelta(minutes=90))
    assert [item['prediction_id'] for item in board['current']]==['a'*64]
    assert board['summary']['current']==1


def test_future_settlement_is_pending_until_it_was_observed(monkeypatch):
    start=datetime(2026,9,20,20,tzinfo=timezone.utc)
    value=row('a',start-timedelta(minutes=70),start,outcome=True)
    monkeypatch.setattr('sportsbet.picks.quote_evidence_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.settlement_identity_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.verified_settlement_evidence',lambda *args:True)
    pending=build_pick_board([value],'nfl',start+timedelta(hours=3))
    assert pending['history'][0]['result']=='pending'
    assert pending['summary']['settled']==0
    known=build_pick_board([value],'nfl',start+timedelta(hours=4))
    assert known['history'][0]['result']=='win'
    assert known['summary']['settled']==1


def test_naive_publication_time_is_rejected():
    with pytest.raises(ValueError,match='timezone'):
        build_pick_board([],'nfl',datetime(2026,9,20,20))


@pytest.mark.parametrize('actual',[None,True,'300',float('nan'),float('inf')])
def test_malformed_result_stays_pending_without_hiding_the_pick(monkeypatch,actual):
    start=datetime(2026,9,20,20,tzinfo=timezone.utc)
    value=row('a',start-timedelta(minutes=70),start,outcome=True)|{'actual_value':actual}
    monkeypatch.setattr('sportsbet.picks.quote_evidence_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.settlement_identity_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.verified_settlement_evidence',lambda *args:True)
    board=build_pick_board([value],'nfl',start+timedelta(hours=5))
    assert board['history'][0]['result']=='pending'
    assert board['history'][0]['actual_value'] is None
    assert board['summary']['settled']==0


def test_future_capture_cannot_change_an_earlier_board(monkeypatch):
    start=datetime(2026,9,20,20,tzinfo=timezone.utc)
    valid=row('a',start-timedelta(hours=3),start)
    future=row('b',start-timedelta(hours=1),start+timedelta(minutes=30))
    monkeypatch.setattr('sportsbet.picks.quote_evidence_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.settlement_identity_valid',lambda value:True)
    observed=start-timedelta(hours=2)
    assert build_pick_board([valid,future,None,[]],'nfl',observed)==build_pick_board([valid],'nfl',observed)


def test_published_fixture_matches_the_frontend_contract():
    import json
    from pathlib import Path
    from sportsbet.ledger import quote_evidence_valid, verified_settlement_evidence
    fixture=json.loads(Path('tests/fixtures/pick_board_contract.json').read_text())
    record=fixture['record'];board=fixture['board']
    assert quote_evidence_valid(record)
    assert verified_settlement_evidence(record,record['outcome'],record['outcome_source'],
        record['outcome_ref'],record['outcome_observed_at'],record['actual_value'],record['outcome_evidence'])
    assert build_pick_board([record],record['sport'],datetime.fromisoformat(board['generated_at']))==board
    assert board['history'][0]['actual_value']==0


def test_staged_reserve_can_capture_a_verified_pick_before_unchanged_board_lock(tmp_path):
    import json
    from pathlib import Path
    from sportsbet.ledger import Ledger, quote_evidence_valid
    from sportsbet.scan import event_credit_holdback, next_quote_check, prop_credit_holdback
    fixture=json.loads(Path('tests/fixtures/pick_board_contract.json').read_text(encoding='utf-8'))
    record=fixture['record']
    captured=datetime.fromisoformat(record['captured_at'])
    start=datetime.fromisoformat(record['game_start_time'])
    event={'commence_time':start.isoformat()}
    assert captured==start-timedelta(hours=2)
    assert quote_evidence_valid(record)  # Real source commitment; no evidence validator is mocked.
    assert next_quote_check(event,(captured-timedelta(minutes=30)).isoformat(),captured)==captured
    ledger=Ledger(tmp_path/'prelock.sqlite')
    assert ledger.reserve_api_credits(11,20)
    held=prop_credit_holdback(['nfl'],20)
    assert not ledger.reserve_api_credits(4,20,held)  # Previous all-or-nothing reserve blocks this capture.
    assert ledger.reserve_api_credits(4,20,event_credit_holdback(event,held,captured))
    board=build_pick_board([record],'nfl',start-timedelta(minutes=30))
    assert len(board['current'])==1
    assert board['current'][0]['prediction_id']==record['prediction_id']
    assert board['current'][0]['board_state']=='locked'
    assert board['selection_policy_version']=='pregame-t60-v1'
    # One check remains protected before the lock, then fits within the same cap after it.
    assert not ledger.reserve_api_credits(4,20,event_credit_holdback(event,held,captured))
    assert ledger.reserve_api_credits(4,20,event_credit_holdback(event,held,start-timedelta(minutes=30)))
    assert not ledger.reserve_api_credits(4,20)


def test_cfb_activation_retains_history_and_requires_new_policy(monkeypatch):
    from sportsbet.model_contract import CFB_MODEL_VERSION,CFB_HISTORY_POLICY
    monkeypatch.setattr('sportsbet.picks.quote_evidence_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.settlement_identity_valid',lambda value:True)
    old_start=datetime(2026,9,26,20,tzinfo=timezone.utc)
    start=datetime(2026,9,30,20,tzinfo=timezone.utc)
    old=row('a',old_start-timedelta(hours=2),old_start)|{'sport':'cfb','game_id':'old'}
    new=row('b',start-timedelta(hours=2),start)|{'sport':'cfb','model_version':CFB_MODEL_VERSION,
        'history_policy_version':CFB_HISTORY_POLICY,
        'history_observed_before':(start-timedelta(hours=2,minutes=1)).isoformat()}
    now=start-timedelta(minutes=90)
    board=build_pick_board([old,new],'cfb',now)
    assert len(board['history'])==len(board['current'])==1
    assert board['current'][0]['history_policy_version']==CFB_HISTORY_POLICY
    assert board['current'][0]['history_observed_before']==new['history_observed_before']
    assert board['history'][0]['model_version']=='empirical-jeffreys-v4'
    assert 'history_observed_before' not in board['history'][0]
    assert build_pick_board([new|{'history_policy_version':None}],'cfb',now)['current']==[]
    assert len(build_pick_board([new|{'model_version':'empirical-jeffreys-v4'}],'cfb',now)['current'])==1


def test_new_nfl_board_retains_selection_cutoff_without_relabeling_v4(monkeypatch):
    from sportsbet.model_contract import NFL_MODEL_VERSION, NFL_HISTORY_POLICY

    monkeypatch.setattr('sportsbet.picks.quote_evidence_valid', lambda value: True)
    monkeypatch.setattr('sportsbet.picks.settlement_identity_valid', lambda value: True)
    start = datetime(2026, 10, 4, 20, tzinfo=timezone.utc)
    captured = start-timedelta(hours=2)
    source = (captured-timedelta(minutes=1)).isoformat()
    new = row('a', captured, start) | {
        'model_version': NFL_MODEL_VERSION, 'history_policy_version': NFL_HISTORY_POLICY,
        'history_observed_before': source}
    board = build_pick_board([new], 'nfl', start-timedelta(minutes=90))
    assert board['current'][0]['history_observed_before'] == source
    legacy = row('b', captured, start) | {'history_observed_before': source}
    old_board = build_pick_board([legacy], 'nfl', start-timedelta(minutes=90))
    assert 'history_observed_before' not in old_board['current'][0]


def test_board_clarifies_legacy_plan_without_changing_receipt(monkeypatch):
    start = datetime(2026, 9, 20, 20, tzinfo=timezone.utc)
    retained = row('a', start-timedelta(hours=2), start)
    original = [
        '+17.3% probability edge on player_receptions prop market',
        'Approved research stake at capture: 0.7% of bankroll.',
        'Availability: Active.',
    ]
    retained['trade_plan'] = original.copy()
    monkeypatch.setattr('sportsbet.picks.quote_evidence_valid', lambda value: True)
    monkeypatch.setattr('sportsbet.picks.settlement_identity_valid', lambda value: True)
    board = build_pick_board([retained], 'nfl', start-timedelta(hours=1, minutes=30))
    assert board['current'][0]['trade_plan'] == [
        'Model probability minus market implied probability: +17.3 percentage points on player_receptions prop market',
        'Paper sizing at capture (unverified): 0.7% of bankroll.',
        'Availability: Active.',
    ]
    assert retained['trade_plan'] == original


def test_signed_yardage_mean_preserves_valid_quote_contract_without_changing_decision():
    import json
    from copy import deepcopy
    from pathlib import Path
    from sportsbet.nba_source_asof import quote_evidence_valid
    fixture=json.loads(Path('tests/fixtures/pick_board_contract.json').read_text(encoding='utf8'))
    original=fixture['record'];negative=deepcopy(original)|dict(model_mean_stat=-1.25)
    captured=datetime.fromisoformat(original['captured_at'])
    start=datetime.fromisoformat(original['game_start_time'])
    assert quote_evidence_valid(original) and quote_evidence_valid(negative)
    positive=build_pick_board([original],'nfl',start-timedelta(minutes=90))
    expected=deepcopy(positive);expected['current'][0]['mean_stat']=-1.25
    actual=build_pick_board([negative],'nfl',start-timedelta(minutes=90))
    assert actual==expected
    assert negative['captured_at']==original['captured_at']
    assert negative['model_probability']==original['model_probability']
    assert negative['stake_fraction']==original['stake_fraction']
    assert original==fixture['record']
    # Locked and final replay use the same recorded mean and original proof.
    assert build_pick_board([negative],'nfl',start-timedelta(minutes=30))['current'][0]['mean_stat']==-1.25
    final=build_pick_board([negative],'nfl',datetime.fromisoformat(fixture['board']['generated_at']))
    expected_final=deepcopy(fixture['board']);expected_final['history'][0]['mean_stat']=-1.25
    assert final==expected_final


@pytest.mark.parametrize('sport,prop,allowed',[
    ('nfl','pass_yds',True),('nfl','rush_yds',True),('nfl','rec_yds',True),
    ('cfb','pass_yds',True),('cfb','rush_yds',True),('cfb','rec_yds',True),
    ('nfl','receptions',False),('nfl','pass_tds',False),
    ('cfb','receptions',False),('cfb','pass_tds',False),
    ('nba','points',False),('nba','rebounds',False),('nba','assists',False),
])
def test_negative_mean_domain_is_limited_to_signed_football_yards(monkeypatch,sport,prop,allowed):
    start=datetime(2026,9,20,20,tzinfo=timezone.utc)
    value=row('a',start-timedelta(hours=2),start)|dict(sport=sport,prop_type=prop,model_mean_stat=-1.25)
    # This matrix isolates metric-domain validation; the unmocked contract fixture test
    # above independently exercises the unmocked quote/schedule checks.
    monkeypatch.setattr('sportsbet.picks.quote_evidence_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.settlement_identity_valid',lambda value:True)
    assert bool(build_pick_board([value],sport,start-timedelta(minutes=90))['current']) is allowed


@pytest.mark.parametrize('mean',[-10000.01,float('nan'),float('inf'),float('-inf'),'not a number'])
def test_signed_mean_does_not_disable_numeric_bounds_or_hide_valid_neighbor(monkeypatch,mean):
    start=datetime(2026,9,20,20,tzinfo=timezone.utc)
    invalid=row('b',start-timedelta(hours=2),start)|dict(model_mean_stat=mean,game_id='other')
    valid=row('a',start-timedelta(hours=2),start)
    monkeypatch.setattr('sportsbet.picks.quote_evidence_valid',lambda value:True)
    monkeypatch.setattr('sportsbet.picks.settlement_identity_valid',lambda value:True)
    result=build_pick_board([invalid,valid],'nfl',start-timedelta(minutes=90))
    assert [item['prediction_id'] for item in result['current']]==['a'*64]


def test_recent_context_survives_immutable_ledger_and_board_without_later_retrofit(tmp_path):
    import json
    from copy import deepcopy
    from datetime import date
    from pathlib import Path
    from sportsbet.ledger import Ledger
    from sportsbet.prop.recent_participation import recent_participation
    fixture=json.loads(Path('tests/fixtures/pick_board_contract.json').read_text(encoding='utf8'))
    record=deepcopy(fixture['record']);original=deepcopy(record)
    cutoff=date.fromisoformat(record['forecast_cutoff'])
    capture=record['availability']['captured_at'];team=record['availability']['team']
    recent=recent_participation(dict(active=[(cutoff-timedelta(days=60),3),(cutoff-timedelta(days=10),0)],
        absent=[],unknown=[(cutoff-timedelta(days=5),10)]),cutoff,record['line'],record['direction'])
    report=dict(player='Context fixture',position='WR',status='Questionable',team=team,relationship='teammate',
        unit='offense',reported_at=capture,source_url=record['availability']['source_url'],source_sha256=record['availability']['source_sha256'])
    # Controlled context fixture exercises serialization, not real injury or
    # participation-source authentication. The original quote contract is valid.
    split=report|dict(source='nflverse_snap_counts',participation='recorded unit snaps',
        evidence_version='recorded-participation-v3',active=dict(games=2,mean=1.5,hit_rate=.5),
        absent=dict(games=0,mean=None,hit_rate=None),unknown_games=1,recent_window=recent,
        sample_window=dict(cutoff=cutoff.isoformat(),active=dict(oldest=(cutoff-timedelta(days=60)).isoformat(),newest=(cutoff-timedelta(days=10)).isoformat()),
            absent=None,unknown=dict(oldest=(cutoff-timedelta(days=5)).isoformat(),newest=(cutoff-timedelta(days=5)).isoformat())),
        source_rows=[dict(private='fixture proof')],tenure_rows=[dict(private='fixture proof')])
    record['availability'].update(teammates=[report],context_splits=[split])
    ledger=Ledger(tmp_path/'context.sqlite');identity=ledger.record('recent-context',record)
    retained=ledger.predictions();assert retained[0]['prediction_id']==identity
    assert retained[0]['availability']['context_splits'][0]==split
    start=datetime.fromisoformat(record['game_start_time'])
    board=build_pick_board(retained,'nfl',start-timedelta(minutes=30))
    assert board['current'][0]['availability']['context_splits'][0]==split
    assert board['current'][0]['true_prob']==original['model_probability']
    changed=deepcopy(record);changed['availability']['context_splits'][0]['recent_window']['active']['mean']=99
    with pytest.raises(ValueError,match='immutable evidence'):ledger.record('recent-context',changed)
    assert ledger.predictions()==retained
    assert fixture['record']==original
