from decimal import Decimal

import pytest

from sportsbet.quant.kalshi_stat_only_recent_gap import membership, _score_groups


def candidate(ticker, game, side, probability):
    return {'ticker':ticker,'milestone_id':game,'side':side,
            'model_win_probability':probability}


def forecast(ticker, game, probability, player):
    return {'ticker':ticker,'milestone_id':game,'model_over_probability':probability,
            'gsis_player_id':player}


def test_recent_gap_membership_binds_side_and_exact_forecast():
    yes=candidate('A','G1','yes','0.70')
    no=candidate('B','G2','no','0.70')
    assert membership(yes,forecast('A','G1','0.70','P1'),Decimal('.65'))=='model_uplift_ge_5pp'
    assert membership(no,forecast('B','G2','0.30','P2'),Decimal('.35'))=='model_uplift_ge_5pp'
    assert membership(yes,forecast('A','G1','0.70','P1'),Decimal('.66'))=='other'
    with pytest.raises(ValueError):
        membership(yes,forecast('A','G1','0.69','P1'),Decimal('.65'))
    with pytest.raises(ValueError):
        membership(no,forecast('B','G3','0.30','P2'),Decimal('.35'))


def test_recent_gap_scores_fixed_groups_and_keeps_pending_denominator():
    groups={'model_uplift_ge_5pp':[candidate('A','G1','yes','0.8')],
            'other':[candidate('B','G2','no','0.6')]}
    forecasts={'forecasts':[forecast('A','G1','0.8','P1'),
                            forecast('B','G2','0.4','P2')]}
    control={'forecast_rows':[{'ticker':'A','prior20_over_probability':'0.7'},
                              {'ticker':'B','prior20_over_probability':'0.42'}]}
    prices={'A':('two_sided_exact',Decimal('.6'),None,None),
            'B':('two_sided_exact',Decimal('.45'),None,None)}
    states={'A':('venue_verified','yes'),'B':('unsettled',None)}
    report=_score_groups(groups,forecasts,control,prices,states,
                        settlement_sha256='a'*64)
    uplift=report['groups']['model_uplift_ge_5pp']
    assert uplift['fixed_candidates']==uplift['verified_candidates']==1
    assert uplift['paired_scores']['model']['brier']=='0.04'
    assert uplift['paired_scores']['strict_prior20']['brier']=='0.09'
    assert uplift['paired_scores']['market']['brier']=='0.16'
    assert uplift['model_minus_strict_prior20_bounds'] is None
    pending=report['groups']['other']
    assert pending['fixed_candidates']==1 and pending['verified_candidates']==0
    assert pending['full_win_rate'] is None and pending['same_price_paired_results']==0
    assert report['edge_established'] is False and report['qualified_picks']==0
    with pytest.raises(ValueError):
        _score_groups(groups,forecasts,control,prices,states | {'B':('unsettled','no')},
                     settlement_sha256='a'*64)
    with pytest.raises(ValueError):
        _score_groups(groups,forecasts,control,prices,states,
                      settlement_sha256='not-a-real-commitment')


def test_recent_gap_only_reports_cluster_intervals_with_independent_games_and_players():
    groups={'model_uplift_ge_5pp':[candidate('A','G1','yes','0.8'),
                                   candidate('C','G3','yes','0.8')]}
    forecasts={'forecasts':[forecast('A','G1','0.8','P1'),
                            forecast('C','G3','0.8','P3')]}
    control={'forecast_rows':[{'ticker':ticker,'prior20_over_probability':'0.7'}
                              for ticker in ('A','C')]}
    prices={ticker:('two_sided_exact',Decimal('.6'),None,None)
            for ticker in ('A','C')}
    states={'A':('venue_verified','yes'),'C':('venue_verified','no')}
    report=_score_groups(groups,forecasts,control,prices,states,
                         settlement_sha256='a'*64)
    group=report['groups']['model_uplift_ge_5pp']
    assert group['same_price_paired_games']==group['same_price_paired_players']==2
    assert group['model_minus_strict_prior20_bounds']['model_minus_prior20_brier_game_cluster_95']
    assert group['full_win_rate']=='0.5'
    assert report['probability_support'] is False
