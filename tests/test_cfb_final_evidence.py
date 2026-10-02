from copy import deepcopy
from datetime import datetime,timezone
import json
import pytest
from sportsbet.ingestion.cfb_final_evidence import SUMMARY,GAMELOG,digest,inspect_bundle,plan_recovery
from sportsbet.ledger import Ledger,VERIFIED_SETTLEMENT_SOURCE

NOW=datetime(2026,9,29,tzinfo=timezone.utc)
EVENT='999999991';PLAYER='201';START='2026-09-26T00:00:00Z'


def receipt(url,data,observed='2026-09-28T00:00:00Z'):
    raw=json.dumps(data)
    return dict(url=url,response_text=raw,sha256=digest(raw),observed_at=observed)


def bundle():
    teams=[dict(id='84',homeAway='home',score='29',team=dict(id='84',displayName='Indiana Hoosiers',abbreviation='IU')),
           dict(id='77',homeAway='away',score='23',team=dict(id='77',displayName='Northwestern Wildcats',abbreviation='NU'))]
    summary=dict(header=dict(id=EVENT,season=dict(year=2026,type=2),week=4,league=dict(slug='college-football'),
        competitions=[dict(id=EVENT,date=START,status=dict(type=dict(completed=True,name='STATUS_FINAL')),competitors=teams)]),
        boxscore=dict(players=[dict(team=dict(id='84'),statistics=[dict(name='rushing',labels=['CAR','YDS'],
            athletes=[dict(athlete=dict(id=PLAYER,displayName='Fixture Player'),stats=['9','68'])])]),
            dict(team=dict(id='77'),statistics=[])]))
    gamelog=dict(filters=[dict(name='league',value='college-football'),dict(name='season',value='2026')],
        categories=[dict(name='rushing',count=2),dict(name='receiving',count=2)],
        names=['rushingAttempts','rushingYards','receptions','receivingYards'],
        events={EVENT:dict(id=EVENT,gameDate=START,week=4,homeTeamId='84',awayTeamId='77',
            homeTeamScore='29',awayTeamScore='23',team=dict(id='84'),opponent=dict(id='77'))},
        seasonTypes=[dict(categories=[dict(type='event',splitType='2',events=[dict(eventId=EVENT,stats=['9','68','0','0'])])])])
    return dict(version=1,players=[dict(player_id=PLAYER,espn_event_id=EVENT,date='2026-09-25')],sources=[
        receipt(SUMMARY+EVENT,summary),receipt(GAMELOG.format(player=PLAYER,season=2026),gamelog,'2026-09-28T00:01:00Z')])


def prediction(**updates):
    return dict(sport='cfb',game_id='recorded-offer',player='Fixture Player',player_id=PLAYER,
        home_team='Indiana Hoosiers',away_team='Northwestern Wildcats',game_date='2026-09-25',
        game_start_time=START,captured_at='2026-09-25T22:00:00Z',prop_type='receptions',direction='under',
        line=.5,prediction_id='one',outcome=None,sportsbook='book',american_odds=-110,model_probability=.6)|updates


def change(b,index,fn):
    r=b['sources'][index];data=json.loads(r['response_text']);fn(data)
    r.update(response_text=json.dumps(data),sha256=digest(json.dumps(data)))


def test_explicit_zero_roundtrips_and_does_not_change_forecast(tmp_path):
    evidence=inspect_bundle(bundle(),now=NOW);item,=evidence
    assert item['stat_row']['receptions']==item['stat_row']['receiving_yards']==0
    assert item['stat_row']['game_date']=='2026-09-26' and item['game']['date']=='2026-09-25'
    ledger=Ledger(tmp_path/'audit.sqlite');p=prediction();p.pop('prediction_id');p.pop('outcome')
    key=ledger.record('scan',p);before=deepcopy(ledger.predictions());plan=plan_recovery(before,evidence)
    update,=plan['updates'];assert update['outcome'] is True and before==ledger.predictions()
    ledger.settle({key:True},source=VERIFIED_SETTLEMENT_SOURCE,source_ref=update['source_ref'],
        observed_at=NOW,actual_values={key:0},evidence={key:update['evidence']})
    assert ledger.report()['settled_count']==1
    assert plan_recovery(ledger.predictions(),evidence)['updates']==[]


@pytest.mark.parametrize(('direction','line','outcome'),[('under',.5,True),('over',.5,False),('under',0,'push')])
def test_original_terms_determine_zero_result(direction,line,outcome):
    p=prediction(direction=direction,line=line)
    assert plan_recovery([p],inspect_bundle(bundle(),now=NOW))['updates'][0]['outcome']==outcome


@pytest.mark.parametrize(('index','mutate'),[
    (0,lambda d:d['header'].update(id='1')),
    (0,lambda d:d['header']['competitions'][0]['status']['type'].update(completed=False)),
    (0,lambda d:d['header']['season'].update(type=3)),
    (0,lambda d:d['boxscore']['players'][0]['statistics'][0]['athletes'][0].update(stats=['9','69'])),
    (0,lambda d:d['boxscore']['players'][0]['statistics'][0]['athletes'].append(deepcopy(d['boxscore']['players'][0]['statistics'][0]['athletes'][0]))),
    (0,lambda d:d['boxscore']['players'][1].update(statistics=deepcopy(d['boxscore']['players'][0]['statistics']))),
    (1,lambda d:d['filters'][1].update(value='2025')),
    (1,lambda d:d['events'][EVENT].update(homeTeamScore='28')),
    (1,lambda d:d['events'][EVENT].update(gameDate='2026-09-26T00:10:00Z')),
    (1,lambda d:d['events'][EVENT]['team'].update(id='77')),
    (1,lambda d:d['events'][EVENT]['opponent'].update(id='84')),
    (1,lambda d:d['names'].__setitem__(3,'receptions')),
    (1,lambda d:d['seasonTypes'][0]['categories'][0].update(splitType='3')),
    (1,lambda d:d['seasonTypes'][0]['categories'][0]['events'].append(deepcopy(d['seasonTypes'][0]['categories'][0]['events'][0]))),
    (1,lambda d:d['seasonTypes'][0]['categories'][0]['events'][0]['stats'].__setitem__(2,None)),
    (1,lambda d:d['seasonTypes'][0]['categories'][0]['events'][0]['stats'].__setitem__(2,True)),
    (1,lambda d:d['seasonTypes'][0]['categories'][0]['events'][0]['stats'].__setitem__(2,'-1')),
    (1,lambda d:d['seasonTypes'][0]['categories'][0]['events'][0]['stats'].__setitem__(2,'0.5')),
    (1,lambda d:d['seasonTypes'][0]['categories'][0]['events'][0]['stats'].__setitem__(3,'10')),
    (1,lambda d:d['seasonTypes'][0]['categories'][0]['events'][0]['stats'].pop()),
])
def test_ambiguous_conflicting_or_nonfinal_evidence_is_rejected(index,mutate):
    b=bundle();change(b,index,mutate)
    with pytest.raises((ValueError,KeyError)):inspect_bundle(b,now=NOW)


@pytest.mark.parametrize('mode',['no_game','no_receiving','no_participation'])
def test_missing_evidence_stays_unknown(mode):
    b=bundle()
    if mode=='no_game':change(b,1,lambda d:d['seasonTypes'][0]['categories'][0].update(events=[]))
    if mode=='no_receiving':change(b,1,lambda d:d['names'].__setitem__(2,'otherStat'))
    if mode=='no_participation':change(b,0,lambda d:d['boxscore']['players'][0].update(statistics=[]))
    evidence=inspect_bundle(b,now=NOW)
    assert evidence[0]['status']=='unavailable'
    assert plan_recovery([prediction()],evidence)==dict(updates=[],unresolved=['one'])


@pytest.mark.parametrize('mode',['digest','future','inplay','wrong_url','duplicate_source','duplicate_player'])
def test_source_receipts_bind_identity_and_final_observation(mode):
    b=bundle()
    if mode=='digest':b['sources'][1]['sha256']='0'*64
    if mode=='future':b['sources'][1]['observed_at']='2026-09-30T00:00:00Z'
    if mode=='inplay':b['sources'][1]['observed_at']='2026-09-26T01:00:00Z'
    if mode=='wrong_url':b['sources'][1]['url']=GAMELOG.format(player='999',season=2026)
    if mode=='duplicate_source':b['sources'].append(deepcopy(b['sources'][0]))
    if mode=='duplicate_player':b['players'].append(deepcopy(b['players'][0]))
    with pytest.raises((ValueError,KeyError)):inspect_bundle(b,now=NOW)


@pytest.mark.parametrize('changes',[dict(outcome=False),dict(player_id='999'),dict(home_team='Other'),
    dict(sport='nfl'),dict(prop_type='pass_yds'),dict(line=-1),dict(captured_at='2026-09-26T00:01:00Z')])
def test_unmatched_or_decided_forecasts_are_unchanged(changes):
    assert plan_recovery([prediction(**changes)],inspect_bundle(bundle(),now=NOW))['updates']==[]


def test_atomic_recovery_rejects_mixed_sport_plan_before_database_access():
    from unittest.mock import Mock
    from sportsbet.quant.nfl_final_recovery import apply_plan
    conn=Mock();plan=plan_recovery([prediction()],inspect_bundle(bundle(),now=NOW))
    with pytest.raises(ValueError,match='Mixed recovery sports'):apply_plan(conn,plan)
    with pytest.raises(ValueError,match='Unsupported recovery sport'):apply_plan(conn,plan,sport='nba')
    conn.execute.assert_not_called()

def test_unrelated_event_category_without_events_does_not_hide_valid_final():
    b = bundle()
    change(b, 1, lambda d: d['seasonTypes'][0]['categories'].insert(
        0, dict(type='event', splitType='2')))
    evidence, = inspect_bundle(b, now=NOW)
    assert evidence['status'] == 'verified_explicit_stats'
    assert evidence['stat_row']['receptions'] == 0


def test_target_event_category_without_events_stays_unavailable():
    b = bundle()
    change(b, 1, lambda d: d['seasonTypes'][0]['categories'][0].pop('events'))
    evidence, = inspect_bundle(b, now=NOW)
    assert evidence['status'] == 'unavailable'
    assert evidence['reason'] == 'explicit_game_stats_missing'
