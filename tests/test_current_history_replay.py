from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sportsbet.quant.current_history_replay import History, estimate, stamp
from sportsbet.prop.probability import empirical_outcome_probabilities

UTC=timezone.utc
DECISION=datetime(2026,9,20,12,tzinfo=UTC)
DAY=date(2026,9,21)


def row(**changes):
    return dict(dict(player_id='p',athlete_id=1,season=2026,week=1,team='A',game_date='2026-09-01',
        game_id='g',receiving_yards=0,receptions=0,passing_yards=10,rushing_yards=0,
        source_provider='verified',source_observed_at='2026-09-02T00:00:00+00:00',
        source_sha256='a'*64,source_record_sha256='b'*64,supplement_manifest=None,
        supplement_inserted_at=None),**changes)


def snapshot(rows):
    return dict(nfl_base=deepcopy(rows),nfl_receiving=deepcopy(rows),cfb=deepcopy(rows),
        nfl_games=[dict(season=r['season'],week=r['week'],home_team='A',away_team='B',game_date=r['game_date']) for r in rows],
        cfb_supplement_receipts=[])


def sample(data,sport='nfl',prop='rec_yds'):
    return History(data).sample(sport,'p' if sport=='nfl' else '1',prop,DAY,DECISION)


@pytest.mark.parametrize('sport',['nfl','cfb'])
def test_explicit_zero_is_kept_but_null_is_not(sport):
    got,excluded=sample(snapshot([row(),row(week=2,game_id='g2',receiving_yards=None)]),sport)
    assert len(got)==1 and got[0][1]==0
    assert excluded['missing_stat']==1


@pytest.mark.parametrize('sport',['nfl','cfb'])
def test_cutoff_is_exclusive_and_source_time_is_inclusive(sport):
    rows=[row(source_observed_at=DECISION.isoformat()),row(week=2,game_id='g2',game_date=DAY.isoformat()),
          row(week=3,game_id='g3',source_observed_at='2026-09-20T12:00:00.000001+00:00')]
    got,excluded=sample(snapshot(rows),sport)
    assert len(got)==1
    assert excluded['source_unavailable_at_decision']==1
    assert excluded['not_before_game_cutoff_or_missing_schedule']==1


@pytest.mark.parametrize('sport',['nfl','cfb'])
def test_later_inserted_supplements_cannot_leak_into_replay(sport):
    data=snapshot([row(supplement_manifest='receipt',supplement_inserted_at='2026-09-29T00:00:00+00:00')])
    data['cfb_supplement_receipts']=[[1,'g','2026-09-29T00:00:00+00:00','a'*64]]
    assert sample(data,sport)[0]==[]
    if sport=='cfb': data['cfb_supplement_receipts'][0][2]=DECISION.isoformat()
    else: data['nfl_receiving'][0]['supplement_inserted_at']=DECISION.isoformat()
    assert len(sample(data,sport)[0])==1


def test_cfb_receipt_must_match_source_commitment():
    data=snapshot([row(supplement_manifest='receipt')])
    data['cfb_supplement_receipts']=[[1,'g',DECISION.isoformat(),'c'*64]]
    assert sample(data,'cfb')[0]==[]


def test_nfl_schedule_uses_players_team_and_actual_date():
    data=snapshot([row()]);data['nfl_games'][0]['home_team']='C';data['nfl_games'][0]['away_team']='D'
    assert sample(data)[0]==[]


@pytest.mark.parametrize('sport',['nfl','cfb'])
def test_duplicate_game_keys_fail_closed(sport):
    got,excluded=sample(snapshot([row(),row(receiving_yards=90)]),sport)
    assert got==[] and excluded['duplicate_history_key']==1


def test_source_receipt_required_for_passing_too():
    data=snapshot([row(source_observed_at=None),row(week=2,source_record_sha256='bad')])
    assert sample(data,prop='pass_yds')[0]==[]


def test_last_40_applied_after_source_and_stat_filters():
    rows=[row(season=2024+i//20,week=i%20+1,game_date=f'{2024+i//20}-09-01',game_id=str(i),receiving_yards=i) for i in range(45)]
    rows.append(row(season=2026,week=9,game_date='2026-09-19',source_observed_at='2026-09-29T00:00:00+00:00'))
    got,excluded=sample(snapshot(rows))
    assert len(got)==40 and got[0][1]==44 and got[-1][1]==5
    assert excluded['outside_last_40']==5


def test_half_line_and_probability_match_production_function():
    history=[((2026,1),10,'a'*64),((2026,2),11,'b'*64)]
    result=estimate(history,10.5)
    expected=empirical_outcome_probabilities(1,0,2)
    assert result['p']==float(expected[0].quantize(Decimal('0.000001')))==.5
    assert result['pushes']==0 and result['mean']==10.5
    assert estimate(history,10)['push_probability']==.5
    assert estimate([],10) is None


def test_naive_source_timestamp_rejected():
    assert stamp('2026-09-01T00:00:00') is None
    assert stamp('invalid') is None


def test_nfl_insert_cutoff_applies_even_without_manifest():
    data=snapshot([row(supplement_inserted_at="2026-09-29T00:00:00+00:00")])
    assert sample(data)[0]==[]
