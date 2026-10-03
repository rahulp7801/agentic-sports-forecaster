"""Prospective context cannot replace unknowns, backfill old results or promote picks."""
from datetime import datetime, timezone
from decimal import Decimal
import copy
import json

import pytest

from sportsbet.quant import kalshi_stat_only_next_teammate_study as study

NOW = datetime(2026, 10, 8, 17, 25, tzinfo=timezone.utc)
PRIMARY = 'questionable_teammate_only'


def sources():
    roster = [dict(season=2026, game_type='REG', week=5, team='NYJ', gsis_id=player, status='ACT')
              for player in ('subject','teammate','other')]
    injury = [dict(season=2026, season_type='REG', week=5, team='NYJ', gsis_id='teammate',
                   position='WR', report_status='Questionable')]
    schedule = [dict(season=2026, game_type='REG', week=week, gameday=f'2026-09-{6+7*(week-1):02d}',
                     home_team='NYJ', away_team='DAL') for week in (1,2,3)]
    stats = [dict(season=2026, season_type='REG', week=week, team='NYJ', player_id=player, targets=targets)
             for week in (1,2,3) for player,targets in (('subject',6),('teammate',4))]
    return roster, injury, stats, schedule


def member(data=None):
    return study.membership('subject','NYJ',2026,5,*(data or sources()),before=NOW)


def test_questionable_membership_does_not_need_history_or_claim_participation():
    roster, injuries, _, schedule = sources()
    result = member((roster,injuries,[],schedule))
    assert result['teammate_context_stratum'] == PRIMARY
    assert result['acute_target_share'] == '0'
    assert result['subject_report_status'] == 'not_listed'
    assert study.POLICY['causal_effect'] is False


@pytest.mark.parametrize('failure', ['empty_roster','old_week','wrong_team','subject_inactive',
    'subject_duplicate','subject_ambiguous','no_reports','null_status','empty_status',
    'duplicate_report','unknown_report_identity','null_position','ambiguous_teammate'])
def test_missing_or_ambiguous_current_coverage_never_becomes_healthy(failure):
    roster, injuries, stats, schedule = sources()
    if failure == 'empty_roster': roster = []
    elif failure == 'old_week':
        for row in roster: row['week'] = 4
    elif failure == 'wrong_team': roster[0]['team'] = 'DAL'
    elif failure == 'subject_inactive': roster[0]['status'] = 'IR'
    elif failure == 'subject_duplicate': roster.append(roster[0].copy())
    elif failure == 'subject_ambiguous': roster.append(dict(roster[0],team='DAL'))
    elif failure == 'no_reports': injuries = []
    elif failure == 'null_status': injuries[0]['report_status'] = None
    elif failure == 'empty_status': injuries[0]['report_status'] = ''
    elif failure == 'duplicate_report': injuries.append(injuries[0].copy())
    elif failure == 'unknown_report_identity': injuries[0]['gsis_id'] = 'unknown'
    elif failure == 'null_position': injuries[0]['position'] = None
    elif failure == 'ambiguous_teammate': roster.append(dict(roster[1],team='DAL'))
    assert member((roster,injuries,stats,schedule))['teammate_context_stratum'] == 'coverage_unavailable'


def test_non_skill_report_can_support_no_reported_skill_risk():
    data = sources()
    data[1][0]['position'] = 'OT'
    data[1][0]['report_status'] = None
    assert member(data)['teammate_context_stratum'] == 'no_reported_skill_teammate_risk'


def test_subject_status_does_not_become_teammate_context():
    data = sources()
    data[1][0]['gsis_id'] = 'subject'
    data[1][0]['report_status'] = 'Out'
    result = member(data)
    assert result['teammate_context_stratum'] == 'no_reported_skill_teammate_risk'
    assert result['subject_report_status'] == 'Out'


@pytest.mark.parametrize('share,label', [(0,'acute_teammate_zero_prior_targets'),
    (1,'acute_teammate_up_to_10pct_prior_targets'),(2,'acute_teammate_10_to_25pct_prior_targets'),
    (4,'acute_teammate_over_25pct_prior_targets')])
def test_acute_bins_use_only_prior_completed_club_games(share,label):
    data = sources()
    data[1][0]['report_status'] = 'Out'
    for row in data[2]:
        row['targets'] = share if row['player_id'] == 'teammate' else 10-share
    data[2].append(dict(data[2][0],week=5,targets=100000))
    assert member(data)['teammate_context_stratum'] == label


@pytest.mark.parametrize('failure', ['missing_week','null_targets','nan_targets','negative_targets',
                                  'duplicate_stats','missing_identity','zero_denominator'])
def test_invalid_acute_target_coverage_stays_unknown(failure):
    data = sources()
    data[1][0]['report_status'] = 'Doubtful'
    if failure == 'missing_week': data[2][:] = [r for r in data[2] if r['week'] != 2]
    elif failure == 'null_targets': data[2][0]['targets'] = None
    elif failure == 'nan_targets': data[2][0]['targets'] = 'NaN'
    elif failure == 'negative_targets': data[2][0]['targets'] = -1
    elif failure == 'duplicate_stats': data[2].append(data[2][0].copy())
    elif failure == 'missing_identity': data[2][0]['player_id'] = None
    elif failure == 'zero_denominator':
        for row in data[2]: row['targets'] = 0
    assert member(data)['teammate_context_stratum'] == 'coverage_unavailable'


def test_jacksonville_aliases_map_to_same_current_club():
    data = sources()
    for collection in data[:3]:
        for row in collection: row['team'] = 'JAX'
    assert study.membership('subject','JAC',2026,5,*data,before=NOW)['teammate_context_stratum'] == PRIMARY


def case(key='a', game='g1', label=PRIMARY, eligible=True, state='venue_verified', priced=True, candidates=True):
    fixture = ('2026-10-11T17:00:00+00:00',game,'otherclub')
    row = dict(ticker='T',milestone_id=game,side='no',model_win_probability='.8',
        high_probability=True,teammate_context_stratum=label,fixture_key=list(fixture),within_context_window=eligible)
    f = dict(ticker='T',milestone_id=game,gsis_player_id=game+'p',model_over_probability='.2')
    prior = dict(ticker='T',prior20_over_probability='.4')
    receipt = dict(rows=[row] if candidates else [], fixtures=[dict(fixture_key=list(fixture),within_context_window=eligible)])
    return (NOW,key*64,receipt,dict(forecast=dict(forecasts=[f]),control=dict(forecast_rows=[prior])),
            {'T':('two_sided_exact' if priced else 'missing',Decimal('.5'),None,None)},
            {'T':(state,'no' if state == 'venue_verified' else None)})


def group(report,label=PRIMARY):
    return report['scopes']['all_prospective_candidates']['strata'][label]


def test_earliest_eligible_capture_owns_unknown_context_despite_later_winner():
    report = study.combine([case(key='b'),case(label='coverage_unavailable')])
    assert group(report)['fixed_candidates'] == 0
    assert group(report,'coverage_unavailable')['fixed_candidates'] == 1
    assert report['candidate_accounting']['duplicate_eligible_candidates_excluded'] == 1
    assert report['candidate_accounting']['all_capture_candidates'] == 2


def test_outside_window_capture_does_not_own_sunday_before_saturday():
    report = study.combine([case(eligible=False),case(key='b')])
    assert group(report)['fixed_candidates'] == 1
    assert report['candidate_accounting']['outside_context_window_candidates'] == 1


def test_fixture_without_candidates_still_owns_entire_game():
    report = study.combine([case(candidates=False),case(key='b')])
    assert group(report)['fixed_candidates'] == 0
    assert report['candidate_accounting']['independent_eligible_games'] == 1


@pytest.mark.parametrize('state,priced', [('void',True),('venue_verified',False)])
def test_missing_outcome_or_price_cannot_be_repaired_with_later_capture(state,priced):
    report = study.combine([case(state=state,priced=priced),case(key='b')])
    assert group(report)['same_price_paired_candidates'] == 0
    assert group(report)['complete_result_and_price_coverage'] is False
    assert report['primary_group_association_supported'] is False


def test_no_side_matches_market_and_recent_history_orientation():
    report = study.combine([case()])
    assert Decimal(group(report)['paired_scores']['model']['brier']) == Decimal('.04')
    assert Decimal(group(report)['paired_scores']['strict_prior20']['brier']) == Decimal('.16')
    assert group(report)['model_minus_market_bounds'] is None


def test_even_perfect_large_synthetic_signal_never_promotes_picks():
    report = study.combine([case(key=str(i),game=f'g{i}') for i in range(50)])
    assert group(report)['same_price_paired_games'] == 50
    assert report['primary_group_association_supported'] is True
    assert report['edge_established'] is False and report['qualified_picks'] == 0
    assert report['causal_context_effect_established'] is False and report['roi'] is None
    assert len(report['scopes']['all_prospective_candidates']['strata']) == 7


def test_missing_original_primary_group_candidate_blocks_support():
    report = study.combine([*[case(key=str(i),game=f'g{i}') for i in range(50)],case(key='z',game='gap',priced=False)])
    assert group(report)['same_price_paired_games'] == 50
    assert report['primary_group_association_supported'] is False


def test_old_motivating_cohort_cannot_receive_prospective_receipt(tmp_path):
    values = dict(decisions=dict(decided_at='2026-10-04T13:15:00+00:00'))
    with pytest.raises(ValueError,match='new, pregame'):
        study.build(values,tmp_path,dict(first_selected_start_at='2026-10-04T17:00:00+00:00'),now=NOW)


@pytest.mark.parametrize('change',['policy','implementation','row','recorded_at'])
def test_membership_or_protocol_tampering_cannot_replay(change,tmp_path,monkeypatch):
    original = dict(recorded_at=NOW.isoformat(),policy=study.POLICY.copy(),implementation={'score':'a'},rows=[{'ticker':'T'}])
    monkeypatch.setattr(study,'build',lambda *args,**kwargs: copy.deepcopy(original))
    receipt = copy.deepcopy(original)
    if change == 'policy': receipt['policy']['primary_group'] = 'winning_group'
    elif change == 'implementation': receipt['implementation']['score'] = 'b'
    elif change == 'row': receipt['rows'] = []
    elif change == 'recorded_at': receipt['recorded_at'] = '2026-10-12T17:00:00+00:00'
    with pytest.raises(ValueError,match='changed'):
        study.verify_receipt(receipt,{},tmp_path,{})


@pytest.mark.parametrize('change',['marker','late_receipt','primary_proof'])
def test_server_anchor_not_git_author_time_is_required(change,monkeypatch):
    receipt = dict(recorded_at=NOW.isoformat(),commitment_sha256='a'*64,
                   policy=study.POLICY.copy(),implementation={})
    def primary(*args):
        if change == 'primary_proof': raise ValueError('Server push proof missing')
        return dict(remote_pushed_at='2026-10-08T17:26:00+00:00')
    monkeypatch.setattr(study.anchor,'verify',primary)
    saved = study.marker(receipt)
    if change == 'marker': saved['receipt_sha256'] = 'b'*64
    if change == 'late_receipt': receipt['recorded_at'] = '2026-10-08T17:27:00+00:00'; saved = study.marker(receipt)
    monkeypatch.setattr(study.anchor,'_run',lambda *args: json.dumps(saved))
    with pytest.raises(ValueError):
        study.verify_marker(receipt,{},'a'*40,'docs/verification/next-nfl-stat-only-20261008T1700-anchor.json')


def test_private_marker_contains_only_hashes(tmp_path):
    receipt = dict(commitment_sha256='a'*64,policy=study.POLICY.copy(),implementation={},rows=[{'player':'private'}])
    saved = study.marker(receipt)
    assert set(saved) == {'protocol','receipt_sha256','commitment_sha256','policy_sha256','implementation_sha256'}
    assert 'private' not in json.dumps(saved)
    assert study.marker_path(tmp_path/'next-nfl-stat-only-20261008T1700').name == 'next-nfl-context-20261008T1700-anchor.json'


def test_study_failure_stops_before_results(tmp_path,monkeypatch):
    case_input = dict(inputs={},source_dir=tmp_path,commitment={})
    monkeypatch.setattr(study.single,'committed_preflight',lambda *args: ({},{},{}))
    monkeypatch.setattr(study.single,'_input',lambda *args: ({},'a'*64))
    monkeypatch.setattr(study,'verify_receipt',lambda *args: (_ for _ in ()).throw(ValueError('Membership changed')))
    monkeypatch.setattr(study.single,'evaluate',lambda *args,**kwargs: pytest.fail('Result replay before study freeze'))
    with pytest.raises(ValueError,match='Membership changed'):
        study.aggregate([case_input],now=NOW)


def setup_build(tmp_path,monkeypatch,*,hours=7,status='unavailable'):
    from datetime import timedelta
    root = tmp_path / 'next-nfl-stat-only-20261008T1700'
    root.mkdir()
    decided = NOW - timedelta(minutes=20)
    start = decided + timedelta(hours=hours)
    fixture = (start.isoformat(),'NYJ-id','DAL-id')
    source = dict(targets={key:dict(details=dict(abbreviation=club))
                          for key,club in [('NYJ-id','NYJ'),('DAL-id','DAL')]})
    candidate = dict(ticker='T',milestone_id='game',side='no',model_win_probability='.8',displayed_ask='.4')
    values = dict(decisions=dict(decided_at=decided.isoformat(),candidates=[candidate]),
        forecast=dict(forecasts=[dict(ticker='T',milestone_id='game',gsis_player_id='subject',scheduled_game_start_time=start.isoformat())]),
        pair={},market=dict(evidence=dict(sources=dict(kalshi=source))))
    cohort = dict(selections=[dict(ticker='T',team_target_id='NYJ-id')])
    commitment = dict(first_selected_start_at=start.isoformat(),context_receipt_sha256='a'*64)
    schedule = [dict(season=2026,game_type='REG',week=5,gameday=start.astimezone(study.NY).date().isoformat(),home_team='NYJ',away_team='DAL')]
    roster,injuries,stats,_ = sources()
    monkeypatch.setattr(study.context,'verify',lambda *args,**kwargs:'a'*64)
    monkeypatch.setattr(study.single,'_input',lambda *args: (dict(status=status),'b'*64))
    monkeypatch.setattr(study,'unpack',lambda *args:(cohort,{}))
    monkeypatch.setattr(study.series,'_fixture_map',lambda *args:dict(game=fixture))
    def rows(path,columns,limit=2_000_000):
        if path.name == 'schedule.parquet': return schedule
        if path.name.startswith('roster'): return roster
        if path.name.startswith('injuries'): return injuries
        return stats
    monkeypatch.setattr(study,'_rows',rows)
    return root,values,commitment


@pytest.mark.parametrize('hours,eligible',[(7,True),(48,True),(48.01,False),(72,False)])
def test_frozen_decision_clock_controls_inclusive_48_hour_window(tmp_path,monkeypatch,hours,eligible):
    root,values,commitment = setup_build(tmp_path,monkeypatch,hours=hours)
    report = study.build(values,root/'sources',commitment,now=NOW)
    assert report['fixed_candidates'] == 1
    assert report['rows'][0]['within_context_window'] is eligible
    assert report['fixtures'][0]['within_context_window'] is eligible
    assert report['rows'][0]['teammate_context_stratum'] == 'coverage_unavailable'


def test_full_build_replays_same_membership_without_reading_results(tmp_path,monkeypatch):
    root,values,commitment = setup_build(tmp_path,monkeypatch,status='observed')
    report = study.build(values,root/'sources',commitment,now=NOW)
    assert report['rows'][0]['teammate_context_stratum'] == PRIMARY
    study.verify_receipt(report,values,root/'sources',commitment)
    report['rows'][0]['quoted_current_team'] = 'OLD_TEAM'
    with pytest.raises(ValueError,match='changed'):
        study.verify_receipt(report,values,root/'sources',commitment)


def test_changed_context_raw_hash_blocks_new_receipt(tmp_path,monkeypatch):
    root,values,commitment = setup_build(tmp_path,monkeypatch)
    commitment['context_receipt_sha256'] = 'c'*64
    with pytest.raises(ValueError,match='differs from primary'):
        study.prepare(root,values,commitment,now=NOW)
    assert not (root/'teammate-study.json').exists()


def test_exclusive_prepare_preserves_receipt_and_refuses_overwrite(tmp_path,monkeypatch):
    root,values,commitment = setup_build(tmp_path,monkeypatch,status='observed')
    path,saved = study.prepare(root,values,commitment,now=NOW)
    raw = (root/'teammate-study.json').read_bytes()
    assert path == study.marker_path(root)
    assert saved == study.marker(json.loads(raw))
    with pytest.raises(ValueError,match='already exists'):
        study.prepare(root,values,commitment,now=NOW)
    assert raw == (root/'teammate-study.json').read_bytes()


@pytest.mark.parametrize('metadata',[None,{},dict(details={}),dict(details=dict(abbreviation=None))])
def test_optional_opponent_metadata_gap_retains_whole_fixture_and_candidate(tmp_path,monkeypatch,metadata):
    root,values,commitment = setup_build(tmp_path,monkeypatch,status='observed')
    targets = values['market']['evidence']['sources']['kalshi']['targets']
    if metadata is None: targets.pop('DAL-id')
    else: targets['DAL-id'] = metadata
    report = study.build(values,root/'sources',commitment,now=NOW)
    assert report['fixed_candidates'] == 1 and len(report['fixtures']) == 1
    assert report['rows'][0]['teammate_context_stratum'] == 'coverage_unavailable'
    assert report['rows'][0]['coverage_reason'] == 'exact_fixture_schedule_unavailable'
    study.verify_receipt(report,values,root/'sources',commitment)


def test_authenticated_but_unsupported_parquet_schema_is_explicit_unknown(tmp_path,monkeypatch):
    reader = study._rows
    root,values,commitment = setup_build(tmp_path,monkeypatch,status='observed')
    original = study._rows
    path = root/'context'/'roster_weekly_2026.parquet'
    path.parent.mkdir()
    study.pq.write_table(study.pa.table({'season':[2026], 'game_type':['REG'],
        'week':[5], 'team':['NYJ'], 'gsis_id':['subject']}),path)
    def changed(path,*args):
        if path.name.startswith('roster'): return reader(path,*args)
        return original(path,*args)
    monkeypatch.setattr(study,'_rows',changed)
    _,saved = study.prepare(root,values,commitment,now=NOW)
    report = json.loads((root/'teammate-study.json').read_text())
    assert saved == study.marker(report)
    assert report['source_status'] == 'observed'
    assert report['study_source_status'] == 'context_schema_unavailable'
    assert report['fixed_candidates'] == 1 and len(report['fixtures']) == 1
    assert report['rows'][0]['coverage_reason'] == 'context_schema_unavailable'
    study.verify_receipt(report,values,root/'sources',commitment)


def test_source_integrity_failure_is_not_downgraded_to_optional_gap(tmp_path,monkeypatch):
    root,values,commitment = setup_build(tmp_path,monkeypatch,status='observed')
    original = study._rows
    def changed(path,*args):
        if path.name.startswith('roster'): raise ValueError('Study source missing or unbounded')
        return original(path,*args)
    monkeypatch.setattr(study,'_rows',changed)
    with pytest.raises(ValueError,match='missing or unbounded'):
        study.prepare(root,values,commitment,now=NOW)
    assert not (root/'teammate-study.json').exists()


@pytest.mark.parametrize('position',['Unknown','EDGE?','',None,4,dict(unit='offense')])
def test_unrecognized_position_cannot_become_no_reported_skill_risk(position):
    data = sources()
    data[1][0]['position'] = position
    data[1][0]['report_status'] = 'Out'
    assert member(data)['teammate_context_stratum'] == 'coverage_unavailable'


@pytest.mark.parametrize('field,value',[('position',4),('week','5'),('gsis_id',123)])
def test_actual_parquet_label_type_drift_is_unavailable_not_a_lookup_crash(tmp_path,field,value):
    columns = dict(season=[2026],season_type=['REG'],week=[5],team=['NYJ'],
        gsis_id=['subject'],position=['WR'],report_status=['Out'])
    columns[field] = [value]
    path = tmp_path/'context.parquet'
    study.pq.write_table(study.pa.table(columns),path)
    with pytest.raises(study.pa.ArrowInvalid,match='Unsupported context'):
        study._rows(path,list(columns))
