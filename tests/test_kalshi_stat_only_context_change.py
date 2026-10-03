import pytest

from sportsbet.quant import kalshi_stat_only_context_change as change


def fixture():
    injury=[dict(season=2026,season_type='REG',week=4,team=f'T{i:02d}',
                 gsis_id=f'fill{i}',position='LB',report_status=None) for i in range(32)]
    roster=[dict(season=2026,week=4,game_type='REG',team=f'T{i:02d}',
                 gsis_id=f'fill{i}',status='ACT') for i in range(32)]
    old_inj=injury+[dict(season=2026,season_type='REG',week=4,team='T00',
                         gsis_id='teammate',position='WR',report_status='Out')]
    new_inj=injury+[dict(season=2026,season_type='REG',week=4,team='T00',
                         gsis_id='A',position='WR',report_status='Out')]
    old_ros=roster+[dict(season=2026,week=4,game_type='REG',team='T00',gsis_id='A',status='ACT'),
                    dict(season=2026,week=4,game_type='REG',team='T01',gsis_id='B',status='ACT')]
    new_ros=[dict(r,status='RES') if r['gsis_id']=='B' else dict(r) for r in old_ros]
    contexts=[dict(ticker='a',historical_team='T00',high_probability=True),
              dict(ticker='b',historical_team='T01',high_probability=False)]
    forecasts=[dict(ticker='a',gsis_player_id='A'),dict(ticker='b',gsis_player_id='B')]
    return contexts,forecasts,old_inj,new_inj,old_ros,new_ros


def test_fixed_denominator_reports_changed_injuries_and_roster_without_reselecting():
    result=change.compare(*fixture())
    assert result['all_candidates']['candidates']==2
    assert result['all_candidates']['subject_report_changed']==1
    assert result['all_candidates']['acute_teammate_set_changed']==1
    assert result['all_candidates']['subject_roster_changed']==1
    assert result['high_probability_candidates']['candidates']==1
    assert result['high_probability_candidates']['subject_now_out_or_doubtful']==1
    assert result['high_probability_candidates']['subject_roster_changed']==0
    assert result['all_changes_zero'] is False


def test_change_audit_rejects_missing_team_and_duplicate_identity():
    contexts,forecasts,old_inj,new_inj,old_ros,new_ros=fixture()
    with pytest.raises(ValueError,match='team coverage'):
        change.compare(contexts,forecasts,[r for r in old_inj if r['team']!='T02'],new_inj,old_ros,new_ros)
    with pytest.raises(ValueError,match='duplicated'):
        change.compare(contexts,forecasts,old_inj,new_inj,old_ros+[dict(old_ros[0])],new_ros)
