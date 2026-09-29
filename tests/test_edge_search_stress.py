from datetime import timedelta
from copy import deepcopy
import pytest
from sportsbet.quant import edge_search_stress as search
from tests.test_market_challengers import item,NOW


def candidate(game='a',player='p',y=1,net=1):
    return dict(x=item(game=game,player=player,y=y),profit=net,probability=.6,ev=.2,decision=NOW)


def test_model_choice_does_not_use_outcomes_or_duplicate_player_exposure():
    a=item(odds=100,p=.7,line=2.5)
    b=item(odds=100,p=.8,line=3.5)
    selection=search.select_model([a,b])
    assert len(selection)==1 and selection[0]['x']['unit'][3]==3.5
    a['y']=1;b['y']=0
    assert [c['x']['unit'] for c in search.select_model([a,b])]==[c['x']['unit'] for c in selection]


def test_model_selection_requires_all_used_prices_to_be_available_and_fresh():
    early=item(odds=100,p=.8)
    late=item(odds=100,p=.4,line=3.5,entry=NOW+timedelta(minutes=6))
    assert search.select_model([early,late])==[]
    assert search.select_model([item(start=NOW)])==[]


def test_market_probability_control_does_not_manufacture_ev():
    assert search.select_model([item(p=.5,q=.5,odds=-110)])==[]
    assert search.select_model([item(p=.5,q=.5,odds=-110)],True)==[]


def test_market_prior_and_probability_orientation_are_correct():
    x=item(p=.8,q=.5,side='under',odds=100)
    assert search.probability(x)==pytest.approx(.2)
    assert search.probability(x,True)==pytest.approx(.44)


def test_repeated_scan_cannot_refresh_decision_and_ambiguous_prices_rejected():
    first=item(p=.8,odds=100)
    later=deepcopy(first);later['entry']+=timedelta(hours=1)
    assert search.select_model([later,first])[0]['decision']==NOW
    conflicting=deepcopy(first);conflicting['row']['american_odds']=150
    assert search.select_model([first,conflicting])==[]


def test_stress_excludes_pending_from_results_and_exposes_game_concentration():
    selected=[candidate('a','p1',1),candidate('a','p2',1),candidate('b','p3',0),candidate('c','p4',None)]
    result=search.metrics(selected)
    assert result['decided']==3 and result['pending']==1
    assert result['flat_stake_roi']==pytest.approx(1/3)
    assert result['roi_without_best_profit_game']==-1
    assert result['leave_one_game_out_roi_range']==[-1,1]
    assert result['pending_all_losses_roi']==0
    assert result['roi_with_lower_winning_payouts']==pytest.approx(.3)


def test_two_sided_margin_is_mathematical_not_model_or_result_based():
    over=item(book='a',side='over',odds=120)
    under=item(book='b',side='under',odds=-110)
    result=search.exact_two_sided_prices([over,under])
    assert result['count']==1
    assert result['examples'][0]['conditional_margin']==pytest.approx(1/(1/2.2+1/(1+100/110))-1)
    over['y']=None;under['y']=0;over['p']=.01
    assert search.exact_two_sided_prices([over,under])==result


@pytest.mark.parametrize('change',[{'book':'a'}, {'source':'different'},{'line':3.5},
    {'quote':NOW-timedelta(seconds=301)},{'start':NOW}])
def test_price_pair_requires_exact_identity_and_timely_distinct_books(change):
    under=item(**(dict(book='b',side='under',odds=-110)|change))
    assert search.exact_two_sided_prices([item(book='a',odds=120),under])['count']==0


def test_equal_break_even_prices_are_not_an_edge_from_decimal_rounding():
    assert search.exact_two_sided_prices([item(book='a',odds=155),item(book='b',side='under',odds=-155)])['count']==0
