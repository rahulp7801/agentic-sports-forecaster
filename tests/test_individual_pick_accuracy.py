from copy import deepcopy
from datetime import datetime,date,timedelta,timezone
import pytest
from sportsbet.quant.individual_pick_accuracy import context,current_role,decide,role_probability,teammate_group,bound_history

NOW=datetime(2026,9,29,tzinfo=timezone.utc)

def fixture():
    rows=[dict(player_id='p',season=2026 if i<2 else 2025,week=3-i if i<2 else 30-i,
        team='A',receiving_yards=0 if i<2 else 20,source_record_sha256=str(i)) for i in range(20)]
    sample=[((r['season'],r['week']),r['receiving_yards'],r['source_record_sha256']) for r in rows]
    return sample,{'nfl_receiving':rows}

def offer(direction='under',y=None):
    return dict(probability=.8,x=dict(y=y,row=dict(line=10.5,direction=direction)))

def availability(**patch):
    return dict(status='observed',roster_confirmed=True,team='A',captured_at=NOW.isoformat(),
        source_sha256='a'*64,roster_source_sha256='b'*64,**patch)

def test_current_role_separates_current_season_team_from_older_history():
    sample,snapshot=fixture()
    role,reason=current_role(sample,snapshot,'nfl','p','rec_yds',date(2026,9,29),'A')
    assert reason is None and role['current']==[0,0] and role['older']==[20]*18
    assert role_probability(role,10.5,'under')==pytest.approx((2+20*.5/19)/22)
    assert role_probability(role,10.5,'over')+role_probability(role,10.5,'under')==pytest.approx(1)

@pytest.mark.parametrize('change,reason',[
    ('duplicate','ambiguous_history_binding'),('wrong_value','invalid_history_binding'),
    ('wrong_week','invalid_history_binding'),('missing','ambiguous_history_binding')])
def test_history_binds_exactly_to_asof_sample(change,reason):
    sample,snapshot=fixture()
    if change=='duplicate':snapshot['nfl_receiving'].append(deepcopy(snapshot['nfl_receiving'][0]))
    if change=='wrong_value':snapshot['nfl_receiving'][0]['receiving_yards']=999
    if change=='wrong_week':snapshot['nfl_receiving'][0]['week']=99
    if change=='missing':snapshot['nfl_receiving'].pop(0)
    assert bound_history(sample,snapshot,'nfl','p','rec_yds')==(None,reason)

def test_team_change_and_insufficient_current_history_abstain():
    sample,snapshot=fixture()
    assert current_role(sample,snapshot,'nfl','p','rec_yds',NOW.date(),'B')[1]=='latest_team_mismatch'
    snapshot['nfl_receiving'][1]['team']='B'
    assert current_role(sample,snapshot,'nfl','p','rec_yds',NOW.date(),'A')[1]=='insufficient_current_role_games'

def test_late_or_stale_or_uncommitted_roster_is_not_current_context():
    a=availability();assert context({'availability':a},NOW)[1] is None
    for patch in [dict(captured_at=(NOW+timedelta(seconds=1)).isoformat()),
        dict(captured_at=(NOW-timedelta(hours=2)).isoformat()),dict(roster_confirmed=False),dict(source_sha256=None)]:
        assert context({'availability':a|patch},NOW)[0] is None

def test_recent_disagreement_blocks_old_high_confidence():
    sample=[(i,20,'x') for i in range(10)]+[(i,0,'x') for i in range(10,40)]
    decision=decide(offer(),sample,{'current':[0,0],'older':[0]*20},7)
    assert decision['original_75'] and not decision['recent_agreement_75']
    assert not decision['recent_and_current_role_75']

def test_current_role_disagreement_blocks_consensus_even_when_recent_agrees():
    sample=[(i,0,'x') for i in range(40)]
    d=decide(offer(),sample,{'current':[20,20],'older':[20]*20},7)
    assert d['recent_agreement_75'] and not d['recent_and_current_role_75']

@pytest.mark.parametrize('gap',[None,-1,31])
def test_old_or_undated_form_never_qualifies(gap):
    d=decide(offer(),[(i,0,'x') for i in range(40)],None,gap)
    assert d['original_75'] and not d['recent_agreement_75']

def test_target_outcome_cannot_change_selection():
    sample=[(i,0,'x') for i in range(40)];role={'current':[0,0],'older':[0]*20}
    a=decide(offer(y=0),sample,role,7)
    assert a==decide(offer(y=1),sample,role,7)==decide(offer(y=None),sample,role,7)
    assert a['recent_and_current_role_75']
    assert not decide(dict(offer(),probability=.74),sample,role,7)['recent_and_current_role_75']

def test_legacy_untyped_or_future_teammate_report_stays_unknown():
    r=dict(status='Out',reported_at=NOW.isoformat())
    assert teammate_group({'teammates':[r]},NOW)=='unknown'
    assert teammate_group({'teammates':[r|{'relationship':'opponent'}]},NOW)=='no_reported_teammate_absence'
    assert teammate_group({'teammates':[r|{'relationship':'teammate'}]},NOW)=='reported_teammate_absence'
    assert teammate_group({'teammates':[r|{'relationship':'teammate','reported_at':(NOW+timedelta(days=1)).isoformat()}]},NOW)=='unknown'
