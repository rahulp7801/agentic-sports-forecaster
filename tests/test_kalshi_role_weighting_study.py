"""Keep current-form research prospective, contemporaneous and fully accounted."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys

import pytest

from sportsbet.quant import kalshi_role_weighting_study as study
from sportsbet.quant.kalshi_market_cohort import digest

NOW = datetime(2026, 10, 8, 17, 0, 10, tzinfo=timezone.utc)


def row(current=3, current_hits=2, old_hits=7, *, ticker='t1', game='g1'):
    older = 20-current
    old = (Decimal(old_hits)+Decimal('.5'))/(older+1)
    return dict(ticker=ticker, milestone_id=game, gsis_player_id='player-'+ticker,
        player_target_id='target-'+ticker, prop_type='rec_yds', line='49.5',
        market_yes_midpoint='.55', sample_games=20, current_team_games=current,
        older_games=older, model_over_probability=float((current_hits+20*old)/(current+20)),
        prior20_over_probability=float((Decimal(current_hits+old_hits)+Decimal('.5'))/21))


def pair(rows=None, *, started=None, extra_offers=None):
    started = started or NOW-timedelta(seconds=2)
    rows = [row()] if rows is None else rows
    offers = [dict(ticker=r['ticker'], milestone_id=r['milestone_id'],
        line=r['line'], prop_type=r['prop_type'], player_target_id=r['player_target_id'],
        received_at=(started-timedelta(seconds=5)).isoformat(), market_midpoint='.55',
        scheduled_game_start_time=(started+timedelta(hours=6)).isoformat()) for r in rows]
    offers.extend(extra_offers or [])
    cohort = dict(selections=offers, selection_sha256=digest(offers), frozen_at=started.isoformat())
    shadow = dict(protocol=study.original.VERSION, generated_at=started.isoformat(),
        forecasts=rows, forecasts_sha256=digest(rows), unavailable_reasons={'missing':len(offers)-len(rows)})
    return dict(protocol='kalshi-nfl-contemporaneous-pair-v1', cohort=cohort, shadow=shadow,
        started_at=started.isoformat(), completed_at=(started+timedelta(seconds=1)).isoformat(),
        market_selection_sha256=cohort['selection_sha256'], forecasts_sha256=shadow['forecasts_sha256'],
        selected_contracts=len(offers), forecast_contracts=len(rows))


@pytest.mark.parametrize('current', range(2,20))
@pytest.mark.parametrize('at_max', [False, True])
def test_exact_hit_recovery_and_current_weight_never_below_prior20(current, at_max):
    hits = current if at_max else 0
    old_hits = 20-current if at_max else 0
    values = study.probabilities(row(current, hits, old_hits))
    assert values['current_hits'] == hits and values['older_hits'] == old_hits
    assert values['prior_strength'] <= min(8,21-current)
    assert Decimal(values['current_weight']) >= Decimal(current)/21
    assert 0 < Decimal(values['capped8']) < 1
    if current == 19:
        assert abs(Decimal(values['capped8'])-Decimal(values['prior20'])) < Decimal('1e-14')


def test_current_form_increases_probability_when_recent_hit_rate_rises():
    values = study.probabilities(row(3,3,0))
    assert Decimal(values['capped8']) > Decimal(values['role20'])
    assert Decimal(values['current_weight']) == Decimal(3)/11


@pytest.mark.parametrize('field,value', [('current_team_games',True), ('older_games',0),
    ('model_over_probability','NaN'), ('prior20_over_probability',1),
    ('model_over_probability',.123456789)])
def test_malformed_or_nonreproducible_role_forecasts_are_rejected(field,value):
    changed = row(); changed[field] = value
    with pytest.raises(ValueError):
        study.probabilities(changed)


def test_freeze_retains_all_props_and_unavailable_denominator():
    rows = [row(ticker='t1'), row(ticker='t2',game='g2')]
    rows[0]['prop_type'] = 'rush_yds'
    rows[1]['prop_type'] = 'pass_yds'
    extra = deepcopy(pair()['cohort']['selections'][0]); extra['ticker']='unavailable'
    value = study.freeze(pair(rows,extra_offers=[extra]), now=NOW)
    assert len(value['forecasts']) == 2
    assert value['original_selected_contracts'] == 3
    assert value['original_role_unavailable'] == 1
    assert {r['prop_type'] for r in value['forecasts']} == {'rush_yds','pass_yds'}
    assert not value['edge_established'] and value['qualified_picks'] == 0


@pytest.mark.parametrize('seconds', [-1,301])
def test_quote_chronology_cannot_be_extended(seconds):
    original = pair()
    quote = datetime.fromisoformat(original['cohort']['selections'][0]['received_at'])
    with pytest.raises(ValueError):
        study.freeze(original,now=quote+timedelta(seconds=seconds))


def test_motivating_october4_cohort_cannot_be_added():
    early = datetime(2026,10,3,13,tzinfo=timezone.utc)
    with pytest.raises(ValueError,match='prospective'):
        study.freeze(pair(started=early),now=early+timedelta(seconds=3))


def test_changed_original_price_or_forecast_hash_rejected():
    changed = pair()
    changed['shadow']['forecasts'][0]['market_yes_midpoint'] = '.99'
    with pytest.raises(ValueError):
        study.freeze(changed,now=NOW)
    changed['shadow']['forecasts_sha256'] = digest(changed['shadow']['forecasts'])
    changed['forecasts_sha256'] = changed['shadow']['forecasts_sha256']
    with pytest.raises(ValueError,match='midpoint'):
        study.freeze(changed,now=NOW)


def setup_case(tmp_path, stamp, value):
    root=tmp_path/'.local'/('next-nfl-stat-only-'+stamp)
    root.mkdir(parents=True)
    receipt=study.freeze(value,now=NOW)
    (root/'role-weighting.json').write_text(json.dumps(receipt),encoding='utf-8')
    commitment=dict(committed_at=(NOW+timedelta(seconds=2)).isoformat(),
        first_selected_start_at=value['cohort']['selections'][0]['scheduled_game_start_time'])
    return dict(inputs={'pair':str(root/'pair.json')},source_dir=str(root/'sources'),
        commitment=commitment,settlements={},anchor_commit_oid='a'*40,
        anchor_marker_path=f'docs/verification/next-nfl-stat-only-{stamp}-anchor.json'),receipt


def test_no_missing_or_after_commitment_role_receipt_can_be_retrofitted(tmp_path):
    value=pair();case,receipt=setup_case(tmp_path,'20261008T1700',value)
    root=Path(case['inputs']['pair']).parent
    commitment=deepcopy(case['commitment']);commitment['committed_at']=(NOW-timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError,match='during original collection'):
        study.prepare(root,{'pair':value},commitment)
    (root/'role-weighting.json').unlink()
    with pytest.raises(ValueError,match='Missing'):
        study.prepare(root,{'pair':value},case['commitment'])


def test_changed_policy_or_implementation_rejected_on_replay(tmp_path):
    value=pair();case,receipt=setup_case(tmp_path,'20261008T1700',value)
    root=Path(case['inputs']['pair']).parent
    receipt['policy']['capped_prior_strength']=4
    (root/'role-weighting.json').write_text(json.dumps(receipt))
    with pytest.raises(ValueError,match='implementation changed'):
        study.prepare(root,{'pair':value},case['commitment'])


def test_role_marker_must_match_same_server_published_commit(monkeypatch):
    receipt=study.freeze(pair(),now=NOW)
    commitment={'first_selected_start_at':(NOW+timedelta(hours=6)).isoformat()}
    monkeypatch.setattr(study.anchor,'verify',lambda *args:{'remote_pushed_at':(NOW+timedelta(seconds=5)).isoformat()})
    saved=study.marker(receipt,commitment)
    paths=[]
    monkeypatch.setattr(study.anchor,'_run',lambda *args:paths.append(args[-1]) or json.dumps(saved))
    study.verify_marker(receipt,commitment,'a'*40,'docs/verification/next-nfl-stat-only-20261008T1700-anchor.json')
    assert paths == ['a'*40+':docs/verification/next-nfl-role-weighting-20261008T1700-anchor.json']
    saved['role_receipt_sha256']='b'*64
    with pytest.raises(ValueError,match='server-published'):
        study.verify_marker(receipt,commitment,'a'*40,'docs/verification/next-nfl-stat-only-20261008T1700-anchor.json')


def test_primary_source_or_full_settlement_failure_precedes_role_score(monkeypatch):
    def fail(*args,**kwargs):
        assert kwargs['verify_remote'] is True
        raise ValueError('Before full cohort settlement gate')
    monkeypatch.setattr(study.series,'aggregate',fail)
    monkeypatch.setattr(study.series.single,'_input',lambda *args:pytest.fail('Read role/result after failed primary gate'))
    with pytest.raises(ValueError,match='full cohort'):
        study.aggregate([{}],now=NOW)


def test_cli_does_not_read_settlement_before_full_original_gate(tmp_path,monkeypatch):
    root=tmp_path/'capture';root.mkdir()
    (root/'commitment.json').write_text('{}')
    (root/'role-weighting.json').write_text('{}')
    paths={key:f'capture/{key}.json' for key in study.series.single.LIMITS}
    paths.update(source_dir='capture/sources',commitment='capture/commitment.json',
        settlements='capture/settlements.json',anchor_commit_oid='a'*40,
        anchor_marker_path='docs/verification/next-nfl-stat-only-20261008T1700-anchor.json')
    manifest=tmp_path/'cases.json';manifest.write_text(json.dumps({'protocol':study.VERSION,'cases':[paths]}))
    monkeypatch.setattr(sys,'argv',['study','--manifest',str(manifest),'--output',str(tmp_path/'score.json')])
    original_input=study.series.single._input
    def read(path,limit):
        assert path.name != 'settlements.json', 'Settlement read before full-cohort gate'
        return original_input(path,limit)
    monkeypatch.setattr(study.series.single,'_input',read)
    monkeypatch.setattr(study.series.single,'committed_preflight',lambda *args:({}, {'first_eligible_settlement_at':'2100-01-01T00:00:00+00:00'}, {}))
    monkeypatch.setattr(study,'prepare',lambda *args:None)
    monkeypatch.setattr(study,'verify_marker',lambda *args:None)
    with pytest.raises(ValueError,match='full-cohort settlement gate'):
        study.main()
    assert not (tmp_path/'score.json').exists()


def test_earliest_whole_fixture_keeps_missing_and_nonbinary_rows(tmp_path,monkeypatch):
    first=pair([row(ticker='first',game='g2')])
    missing=deepcopy(first['cohort']['selections'][0]);missing.update(ticker='missing',milestone_id='g1')
    first=pair([row(ticker='first',game='g2')],extra_offers=[missing])
    later=pair([row(ticker='replacement',game='g1')])
    a,_=setup_case(tmp_path,'20261008T1700',first)
    b,_=setup_case(tmp_path,'20261010T1700',later)
    b['commitment']['committed_at']=(NOW+timedelta(seconds=3)).isoformat()
    values={a['inputs']['pair']:first,b['inputs']['pair']:later}
    monkeypatch.setattr(study.series,'aggregate',lambda *args,**kwargs:{'pregame_commitment_sha256':[digest(a['commitment']),digest(b['commitment'])]})
    monkeypatch.setattr(study.series.single,'committed_preflight',lambda inputs,*args:({'pair':values[inputs['pair']],'market':{}},{},{}))
    monkeypatch.setattr(study,'verify_marker',lambda *args:{})
    monkeypatch.setattr(study.series,'_fixture_map',lambda market,cohort:{r['milestone_id']:('start',r['milestone_id']) for r in cohort['selections']})
    monkeypatch.setattr(study,'venue_results',lambda market,cohort,*args,**kwargs:(None,{r['ticker']:('nonbinary_result',None) for r in cohort['selections']}))
    result=study.aggregate([b,a],now=NOW+timedelta(days=8))
    assert result['original_owned_contracts']==2
    assert result['owned_role_forecasts']==1
    assert result['original_role_unavailable']==1
    assert result['overlap_forecasts_excluded']==1
    assert result['result_states']=={'nonbinary_result':1}
    assert result['paired_binary']==0 and not result['full_forecast_result_coverage']
    assert not result['prospective_predictive_improvement_supported']
    assert not result['edge_established'] and result['roi'] is None


def test_paired_scores_use_original_prices_and_small_sample_cannot_promote(tmp_path,monkeypatch):
    value=pair([row(ticker=f't{i}',game=f'g{i}') for i in range(3)])
    case,_=setup_case(tmp_path,'20261008T1700',value)
    monkeypatch.setattr(study.series,'aggregate',lambda *args,**kwargs:{'pregame_commitment_sha256':[digest(case['commitment'])]})
    monkeypatch.setattr(study.series.single,'committed_preflight',lambda *args:({'pair':value,'market':{}},{},{}))
    monkeypatch.setattr(study,'verify_marker',lambda *args:{})
    monkeypatch.setattr(study.series,'_fixture_map',lambda market,cohort:{r['milestone_id']:('start',r['milestone_id']) for r in cohort['selections']})
    monkeypatch.setattr(study,'venue_results',lambda market,cohort,*args,**kwargs:(None,{r['ticker']:('venue_verified','yes') for r in cohort['selections']}))
    result=study.aggregate([case],now=NOW+timedelta(days=8))
    assert result['paired_binary']==3 and result['paired_independent_games']==3
    assert result['full_forecast_result_coverage']
    assert Decimal(result['paired_scores']['market']['brier'])==Decimal('.2025')
    assert Decimal(result['paired_scores']['capped8']['brier']) < Decimal(result['paired_scores']['role20']['brier'])
    assert result['bounds']['role20']['model_minus_role20_brier_equal_game']
    assert not result['prospective_predictive_improvement_supported']
    assert result['qualified_picks']==0 and not result['market_midpoint_executable']
