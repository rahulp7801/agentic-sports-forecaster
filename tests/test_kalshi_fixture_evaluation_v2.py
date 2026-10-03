from copy import deepcopy
from datetime import datetime, timezone
import pytest
import pyarrow as pa
import pyarrow.parquet as pq
from sportsbet.quant import kalshi_stat_only_next_series_v2 as series
from sportsbet.quant import kalshi_stat_only_next_teammate_study_v2 as study
from sportsbet.quant import kalshi_stat_only_next_recent_gap as recent_v1
from sportsbet.quant import kalshi_stat_only_next_recent_gap_eval_v2 as recent_v2
from sportsbet.quant import kalshi_role_weighting_study as role_v1
from sportsbet.quant import kalshi_role_weighting_eval_v2 as role_v2
from sportsbet.quant.kalshi_pair_series_eval import _game_keys

START='2026-10-09T00:15:00+00:00'
NOW=datetime(2026,10,8,20,tzinfo=timezone.utc)
def fixture():
    game=dict(id='game',start_date=START,details=dict(home_team_id='NYJ-id',away_team_id='DAL-id'))
    source=dict(games=[dict(milestone=game,snapshots=[])],targets={
        'NYJ-id':dict(details=dict(abbreviation='NYJ')),
        'DAL-id':dict(details=dict(abbreviation='DAL'))})
    market=dict(evidence=dict(sources=dict(kalshi=source)))
    cohort=dict(selections=[dict(ticker='T',milestone_id='game',scheduled_game_start_time=START,team_target_id='NYJ-id')])
    return market,cohort

def test_fixture_map_reads_authenticated_nested_milestone_without_mutation():
    market,cohort=fixture(); original=deepcopy(market)
    ids,expected=_game_keys(market,cohort)
    actual=series._fixture_map(market,cohort)
    assert set(actual)==ids and set(actual.values())==expected
    assert market==original
    # Contradictory envelope-level fields never replace the nested source.
    market['evidence']['sources']['kalshi']['games'][0].update(
        details=dict(home_team_id='fake-a',away_team_id='fake-b'),start_date='2027-01-01T00:00:00Z')
    assert series._fixture_map(market,cohort)==actual

@pytest.mark.parametrize('failure',['duplicate_id','duplicate_fixture','changed_start','same_team','missing_details','missing_game'])
def test_fixture_identity_and_chronology_fail_closed(failure):
    market,cohort=fixture(); games=market['evidence']['sources']['kalshi']['games']
    if failure=='duplicate_id': games.append(deepcopy(games[0]))
    elif failure=='duplicate_fixture':
        extra=deepcopy(games[0]);extra['milestone']['id']='second';games.append(extra)
        cohort['selections'].append(dict(cohort['selections'][0],milestone_id='second'))
    elif failure=='changed_start': games[0]['milestone']['start_date']='2026-10-10T00:15:00Z'
    elif failure=='same_team': games[0]['milestone']['details']['away_team_id']='NYJ-id'
    elif failure=='missing_details': del games[0]['milestone']['details']
    else: games.clear()
    with pytest.raises((ValueError,KeyError)):
        series._fixture_map(market,cohort)

def test_existing_role_and_recent_receipts_use_original_frozen_verifiers():
    assert role_v2.freeze is role_v1.freeze
    assert role_v2.prepare is role_v1.prepare
    assert role_v2.verify_marker is role_v1.verify_marker
    assert recent_v2.freeze is recent_v1.freeze
    assert recent_v2.implementation_hash is recent_v1.implementation_hash
    assert role_v2.POLICY is role_v1.POLICY
    assert recent_v2.POLICY is recent_v1.POLICY
    assert role_v2.EVALUATION_VERSION!=role_v1.VERSION
    assert recent_v2.EVALUATION_VERSION!=recent_v1.VERSION

def test_real_envelope_flows_through_versioned_context_build(tmp_path,monkeypatch):
    root=tmp_path/'next-nfl-stat-only-20261008T1700';root.mkdir()
    pq.write_table(pa.Table.from_pylist([dict(season=2026,game_type='REG',week=5,gameday='2026-10-08',home_team='NYJ',away_team='DAL')]),root/'schedule.parquet')
    market,cohort=fixture()
    values=dict(market=market,pair={},decisions=dict(decided_at='2026-10-08T17:00:54Z',candidates=[
        dict(ticker='T',milestone_id='game',side='no',model_win_probability='.8',displayed_ask='.4')]),
        forecast=dict(forecasts=[dict(ticker='T',milestone_id='game',gsis_player_id='subject',scheduled_game_start_time=START)]))
    commitment=dict(first_selected_start_at=START,context_receipt_sha256='a'*64)
    monkeypatch.setattr(study.context,'verify',lambda *args,**kwargs:'a'*64)
    monkeypatch.setattr(study.single,'_input',lambda *args:(dict(status='unavailable'),'b'*64))
    monkeypatch.setattr(study,'unpack',lambda *args:(cohort,{}))
    original=deepcopy(values)
    result=study.build(values,root/'sources',commitment,now=NOW)
    assert result['fixed_candidates']==1 and len(result['fixtures'])==1
    assert result['rows'][0]['fixture_key']==list(series._fixture_map(market,cohort)['game'])
    assert result['rows'][0]['teammate_context_stratum']=='coverage_unavailable'
    assert result['rows'][0]['within_context_window'] is True
    assert result['edge_established'] is False and result['qualified_picks']==0
    assert values==original
    assert result['protocol']==study.VERSION
    assert study.marker_path(root).name=='next-nfl-context-v2-20261008T1700-anchor.json'
    assert {'kalshi_stat_only_next_series_v2.py','kalshi_stat_only_next_recent_gap_eval_v2.py','kalshi_role_weighting_eval_v2.py'} <= result['implementation'].keys()

# Reuse the frozen policy regression inputs/assertions against the v2 report paths.
# These are controlled cases; the nested-envelope tests above do not mock the mapper.
def regression_module(filename):
    import importlib.util
    from pathlib import Path
    path=Path(__file__).with_name(filename)
    spec=importlib.util.spec_from_file_location('_fixture_v2_'+path.stem,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_v2_series_keeps_earliest_server_fixture_and_missing_quote(monkeypatch):
    module=regression_module('test_kalshi_stat_only_next_series.py')
    module.series=series
    module.test_first_pregame_fixture_owns_missing_quote(monkeypatch)

@pytest.mark.parametrize('name',[
    'test_primary_source_or_full_settlement_failure_precedes_role_score',
    'test_earliest_whole_fixture_keeps_missing_and_nonbinary_rows',
    'test_paired_scores_use_original_prices_and_small_sample_cannot_promote'])
def test_v2_role_evaluation_keeps_original_policy(name,tmp_path,monkeypatch):
    module=regression_module('test_kalshi_role_weighting_study.py');module.study=role_v2
    if name=='test_primary_source_or_full_settlement_failure_precedes_role_score':
        getattr(module,name)(monkeypatch)
    else: getattr(module,name)(tmp_path,monkeypatch)

@pytest.mark.parametrize('count,remote,supported',[(49,True,False),(50,False,False),(50,True,True)])
def test_v2_recent_evaluation_requires_50_games_and_remote_proof(monkeypatch,count,remote,supported):
    module=regression_module('test_kalshi_stat_only_next_recent_gap.py')
    module.gap=recent_v2;module.primary=series
    module.test_replication_requires_50_independent_games_and_remote_proof(monkeypatch,count,remote,supported)

@pytest.mark.parametrize('label',['market','strict_prior20'])
def test_v2_recent_evaluation_retains_both_comparator_and_cluster_gates(monkeypatch,label):
    module=regression_module('test_kalshi_stat_only_next_recent_gap.py')
    module.gap=recent_v2;module.primary=series
    module.test_both_comparators_and_both_cluster_intervals_required(monkeypatch,label)

@pytest.mark.parametrize('name',['test_missing_results_remain_in_full_denominator','test_first_remote_commitment_retains_missing_quote'])
def test_v2_recent_evaluation_cannot_repair_original_coverage(monkeypatch,name):
    module=regression_module('test_kalshi_stat_only_next_recent_gap.py')
    module.gap=recent_v2;module.primary=series
    getattr(module,name)(monkeypatch)

@pytest.mark.parametrize('name',[
    'test_earliest_eligible_capture_owns_unknown_context_despite_later_winner',
    'test_outside_window_capture_does_not_own_sunday_before_saturday',
    'test_fixture_without_candidates_still_owns_entire_game',
    'test_even_perfect_large_synthetic_signal_never_promotes_picks',
    'test_missing_original_primary_group_candidate_blocks_support'])
def test_v2_context_evaluation_keeps_ownership_and_support_gates(name):
    module=regression_module('test_kalshi_stat_only_next_teammate_study.py');module.study=study
    getattr(module,name)()

def test_v2_role_cli_keeps_original_full_cohort_gate(tmp_path,monkeypatch):
    import json,sys
    root=tmp_path/'capture';root.mkdir()
    (root/'commitment.json').write_text('{}');(root/'role-weighting.json').write_text('{}')
    paths={key:f'capture/{key}.json' for key in series.single.LIMITS}
    paths.update(source_dir='capture/sources',commitment='capture/commitment.json',
        settlements='capture/settlements.json',anchor_commit_oid='a'*40,
        anchor_marker_path='docs/verification/next-nfl-stat-only-20261008T1700-anchor.json')
    manifest=tmp_path/'cases.json'
    manifest.write_text(json.dumps(dict(protocol=role_v2.EVALUATION_VERSION,cases=[paths])))
    monkeypatch.setattr(sys,'argv',['study','--manifest',str(manifest),'--output',str(tmp_path/'score.json')])
    original=series.single._input
    def read(path,limit):
        assert path.name!='settlements.json','Result read before original full-cohort gate'
        return original(path,limit)
    monkeypatch.setattr(series.single,'_input',read)
    monkeypatch.setattr(series.single,'committed_preflight',lambda *args:({},dict(first_eligible_settlement_at='2100-01-01T00:00:00Z'),{}))
    monkeypatch.setattr(role_v2,'prepare',lambda *args:None)
    monkeypatch.setattr(role_v2,'verify_marker',lambda *args:None)
    with pytest.raises(ValueError,match='full-cohort settlement gate'):
        role_v2.main()
    assert not (tmp_path/'score.json').exists()
