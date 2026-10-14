"""Post-result research cannot reselect winners, drop gaps, or authorize picks."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import copy

import pytest
from sportsbet.quant import kalshi_stat_only_context_price_audit as audit

LABEL='acute_teammate_over_25pct_prior_targets'


def fixture():
    rows=[dict(ticker='A',milestone_id='g1',side='no',model_win_probability='.8',high_probability=True,teammate_context_stratum=LABEL),
          dict(ticker='B',milestone_id='g2',side='yes',model_win_probability='.6',high_probability=False,teammate_context_stratum=LABEL),
          dict(ticker='C',milestone_id='g3',side='no',model_win_probability='.9',high_probability=True,teammate_context_stratum=LABEL)]
    forecasts=[dict(ticker=row['ticker'],milestone_id=row['milestone_id'],gsis_player_id='p'+row['ticker'],
                    model_over_probability={'A':'.2','B':'.6','C':'.1'}[row['ticker']]) for row in rows]
    prior=[dict(ticker=ticker,prior20_over_probability='.4') for ticker in ('A','B','C')]
    prices={ticker:('two_sided_exact',Decimal('.5'),None,None) for ticker in ('A','B','C')}
    states={'A':('venue_verified','no'),'B':('venue_verified','yes'),'C':('venue_nonbinary',None)}
    return rows,forecasts,prior,prices,states


def test_all_original_bins_scopes_and_nonbinary_denominator_are_preserved():
    groups=audit.summarize(*fixture())
    full=groups['all_original_70']['strata'][LABEL]
    assert set(groups['all_original_70']['strata'])==set(audit.STRATA)
    assert full['fixed_candidates']==3 and full['verified_binary_candidates']==2 and full['verified_binary_wins']==2
    assert full['result_counts']=={'venue_nonbinary':1,'venue_verified':2}
    assert full['full_group_win_rate'] is None and not full['complete_result_and_price_coverage']
    assert full['paired_mean_probability']['model']=='.7' or Decimal(full['paired_mean_probability']['model'])==Decimal('.7')
    assert Decimal(full['paired_scores']['model']['brier'])==Decimal('.10')
    assert Decimal(full['paired_scores']['market']['brier'])==Decimal('.25')
    high=groups['original_high_probability_11']['strata'][LABEL]
    assert high['fixed_candidates']==2 and high['verified_binary_wins']==1
    for name,group in groups['all_original_70']['strata'].items():
        if name!=LABEL:assert group['fixed_candidates']==0 and group['full_group_win_rate'] is None


def test_missing_exact_price_retains_candidate_and_binary_result():
    args=fixture();args[3]['B']=('unavailable',None,None,None)
    group=audit.summarize(*args)['all_original_70']['strata'][LABEL]
    assert group['fixed_candidates']==3 and group['verified_binary_candidates']==2
    assert group['same_price_paired_candidates']==1 and group['price_counts']['unavailable']==1
    assert group['model_minus_market_bounds'] is None and group['model_minus_strict_prior20_bounds'] is None


def test_correlated_contracts_in_one_game_cannot_have_cluster_intervals():
    args=fixture()
    for row in args[0]:row['milestone_id']='shared'
    for row in args[1]:row['milestone_id']='shared'
    group=audit.summarize(*args)['all_original_70']['strata'][LABEL]
    assert group['same_price_paired_candidates']==2 and group['same_price_paired_games']==1
    assert group['model_minus_market_bounds'] is None


@pytest.mark.parametrize('change',[
    {'high_probability':False},{'high_probability':1},{'side':'yes'},
    {'milestone_id':'different'},{'model_win_probability':'.81'},{'teammate_context_stratum':'chosen_after_wins'},
])
def test_fixed_context_side_game_probability_and_membership_cannot_change(change):
    args=fixture();args[0][0].update(change)
    with pytest.raises(ValueError):audit.summarize(*args)


def test_missing_and_duplicate_identities_are_rejected():
    args=fixture();args[0].append(copy.deepcopy(args[0][0]))
    with pytest.raises(ValueError,match='Duplicate'):audit.summarize(*args)
    args=fixture();del args[3]['A']
    with pytest.raises(ValueError,match='identity'):audit.summarize(*args)
    args=fixture();args[1].append(copy.deepcopy(args[1][0]))
    with pytest.raises(ValueError,match='Duplicate'):audit.summarize(*args)
    args=fixture();args[2].append(copy.deepcopy(args[2][0]))
    with pytest.raises(ValueError,match='Duplicate'):audit.summarize(*args)


@pytest.mark.parametrize('value',['NaN','Infinity','0','1','-.1',True,None])
def test_invalid_exact_market_probability_fails(value):
    args=fixture();args[3]['A']=('two_sided_exact',value,None,None)
    with pytest.raises(ValueError,match='probability'):audit.summarize(*args)


@pytest.mark.parametrize('state,outcome',[('unavailable','yes'),('venue_nonbinary','no'),('venue_verified',None)])
def test_unverified_and_nonbinary_results_cannot_be_imputed(state,outcome):
    args=fixture();args[4]['C']=(state,outcome)
    with pytest.raises(ValueError,match='outcome'):audit.summarize(*args)


def mocked_evaluation(monkeypatch):
    rows=[dict(ticker=str(i),milestone_id='g'+str(i%15),side='yes',model_win_probability='.8' if i<11 else '.6',
               high_probability=i<11,teammate_context_stratum=LABEL) for i in range(70)]
    forecasts=[dict(ticker=r['ticker'],milestone_id=r['milestone_id'],gsis_player_id='p'+r['ticker'],model_over_probability=r['model_win_probability']) for r in rows]
    prior=[dict(ticker=r['ticker'],prior20_over_probability='.5') for r in rows]
    prices={r['ticker']:('two_sided_exact',Decimal('.5'),None,None) for r in rows}
    states={r['ticker']:('venue_verified','yes') for r in rows}
    pre={'original_market_contracts':70,'first_eligible_settlement_at':'2026-10-06T06:15:00+00:00'}
    monkeypatch.setattr(audit.frozen,'preflight',lambda *a:(pre,prices))
    monkeypatch.setattr(audit.paper,'verify_capture_wrapper',lambda *a:None)
    monkeypatch.setattr(audit.context,'preflight',lambda *a:{})
    monkeypatch.setattr(audit.context,'score',lambda *a,**kw:{'strata':{LABEL:{'candidates':11,'verified':11,'verified_wins':11}}})
    monkeypatch.setattr(audit,'pinned_control',lambda *a:{'forecast_rows':prior})
    monkeypatch.setattr(audit,'unpack',lambda *a:({},{}))
    monkeypatch.setattr(audit,'venue_results',lambda *a,**kw:([{}]*70,states))
    return rows,forecasts,pre


def test_even_perfect_post_result_bins_never_authorize_edge_or_consumer_picks(monkeypatch,tmp_path):
    rows,forecasts,_=mocked_evaluation(monkeypatch)
    control=tmp_path/'control.json';control.write_text('retained')
    result=audit.evaluate({}, {}, {'forecasts':forecasts}, {}, {},tmp_path,tmp_path,tmp_path,
                          {'rows':rows},{'evidence_sha256':'verified'},control,now=datetime(2026,10,6,20,tzinfo=timezone.utc))
    assert result['analysis_defined_after_results'] is True
    assert result['edge_established'] is False and result['qualified_picks']==0
    assert result['prospective_replication'] is False and result['roi'] is None
    assert result['scopes']['all_original_70']['strata'][LABEL]['verified_binary_wins']==70


def test_original_frozen_score_disagreement_is_rejected(monkeypatch,tmp_path):
    rows,forecasts,_=mocked_evaluation(monkeypatch)
    monkeypatch.setattr(audit.context,'score',lambda *a,**kw:{'strata':{LABEL:{'candidates':11,'verified':11,'verified_wins':0}}})
    with pytest.raises(ValueError,match='disagrees'):
        audit.evaluate({}, {}, {'forecasts':forecasts}, {}, {},tmp_path,tmp_path,tmp_path,
                       {'rows':rows},{'evidence_sha256':'verified'},tmp_path/'missing',now=datetime(2026,10,6,20,tzinfo=timezone.utc))


def test_cli_does_not_read_settlements_before_full_result_gate(monkeypatch,tmp_path):
    monkeypatch.setattr(audit.frozen,'_pinned',lambda *a:{})
    monkeypatch.setattr(audit.frozen,'preflight',lambda *a:({'first_eligible_settlement_at':'2030-01-01T00:00:00+00:00'},{}))
    def forbidden(*args):pytest.fail('premature settlement input read')
    monkeypatch.setattr(audit,'_receipt',forbidden)
    argv=['context-price']
    for name in ('pair','market','forecast','quotes','decisions','source-dir','schedule','injuries','receipt','settlements','control','output'):
        argv.extend(['--'+name,str(tmp_path/name)])
    monkeypatch.setattr('sys.argv',argv)
    with pytest.raises(SystemExit) as stopped:audit.main()
    assert stopped.value.code==2 and not (tmp_path/'output').exists()