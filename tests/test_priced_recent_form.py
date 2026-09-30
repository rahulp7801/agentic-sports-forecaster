from datetime import datetime,timedelta,timezone
import pytest
from sportsbet.quant.priced_recent_form import CANDIDATES, predictions, choose, training_rows, accuracy

NOW=datetime(2026,9,29,tzinfo=timezone.utc)


def sample(values):
    return [(str(i),v,'a'*64) for i,v in enumerate(values)]


def test_recent_models_follow_newest_games_and_shrink_to_the_exact_market():
    p=predictions(sample([20]*10+[0]*30),10.5,.4)
    assert p['recent10']>p['half_life8']>p['half_life16']>p['history40']
    assert p['history40']==round(10.5/41,6)
    assert p['recent10_market80']==pytest.approx((10*p['recent10']+80*.4)/90)
    assert p['history40_market80']==pytest.approx((40*p['history40']+80*.4)/120)
    assert .4<p['recent10_market80']<p['recent10']


def test_explicit_zeros_contribute_and_half_lines_do_not_become_pushes():
    p=predictions(sample([10,11]*10),10.5,.5)
    assert p['history40']==.5 and p['recent10']==.5
    assert predictions(sample([0]*20),.5,.5)['history40']==round(.5/21,6)


@pytest.mark.parametrize('n,market',[(19,.5),(20,0),(20,1),(20,float('nan'))])
def test_missing_history_or_market_is_rejected(n,market):
    with pytest.raises(ValueError):predictions(sample([1]*n),.5,market)


def rows():
    result=[]
    for g in range(5):
        for p in range(10):
            probabilities={name:.1 for name in CANDIDATES};probabilities['recent10']=.9
            result.append(dict(unit=(str(g),str(p),'rec_yds',.5),entry=NOW-timedelta(days=3),
                start=NOW-timedelta(days=2),observed=NOW-timedelta(days=1),y=1,candidate_p=probabilities))
    return result


def target(**changes):
    return dict(dict(unit=('target','p','rec_yds',.5),entry=NOW,y=0),**changes)


def test_only_earlier_authenticated_games_choose_the_model():
    name,counts=choose(rows(),target());assert name=='recent10' and counts['games']==5
    assert choose(rows(),target(y=1))==(name,counts)
    late=rows()
    for x in late:x['observed']=NOW
    assert choose(late,target())[0] is None


def test_same_game_and_future_forecasts_are_excluded():
    history=rows()
    assert len(training_rows(history,target(unit=('0','q','rec_yds',.5))))==40
    history[0]['entry']=NOW
    assert len(training_rows(history,target()))==49
    assert choose(history,target())[0] is None


def test_more_lines_cannot_overweight_a_player_or_game():
    baseline=rows();expected=choose(baseline,target())
    extra=[dict(baseline[0],unit=('0','0','rec_yds',n+.5)) for n in range(1,50)]
    actual=choose(baseline+extra,target())
    assert actual[0]==expected[0]
    assert actual[1]['brier_losses']==pytest.approx(expected[1]['brier_losses'])


def test_ties_use_fixed_order():
    history=rows()
    for x in history:x['candidate_p']={name:.5 for name in CANDIDATES}
    assert choose(history,target())[0]=='history40'


def test_accuracy_excludes_pending_without_converting_to_losses():
    c=lambda y:dict(x={'y':y,'row':{'direction':'under'},'unit':('g','p')},profit=1.,probability=.8)
    r=accuracy([c(0),c(1),c(None)])
    assert r['selected']==3 and r['settled']==2 and r['pending']==1
    assert r['wins']==1 and r['win_rate']==.5 and r['mean_predicted_settled']==.8
    assert r['win_rate_game_cluster_95'] is None
