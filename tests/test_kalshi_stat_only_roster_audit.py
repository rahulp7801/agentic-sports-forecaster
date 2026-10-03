import pytest

from sportsbet.quant import kalshi_stat_only_roster_audit as roster


def fixture():
    rows = [dict(season=2026, week=4, game_type='REG', team=f'T{i:02d}',
                 gsis_id=f'fill{i:02d}', status='ACT') for i in range(32)]
    rows.extend([
        dict(season=2026, week=4, game_type='REG', team='T00', gsis_id='subject', status='ACT'),
        dict(season=2026, week=4, game_type='REG', team='T00', gsis_id='teammate', status='RES'),
        dict(season=2026, week=4, game_type='REG', team='T00', gsis_id=None, status='DEV'),
    ])
    injuries = [dict(season=2026, week=4, team='T00', gsis_id='teammate',
                     position='WR', report_status='Out')]
    contexts = [dict(ticker='A', historical_team='T00', high_probability=True)]
    forecasts = [dict(ticker='A', gsis_player_id='subject')]
    return rows, injuries, contexts, forecasts


def test_week4_roster_audit_distinguishes_active_subject_and_reserve_teammate():
    result = roster.summarize(*fixture())
    assert result['subject_candidates'] == result['high_probability_candidates'] == 1
    assert result['subject_states'] == {'same_team_active_roster': 1}
    assert result['high_probability_acute_teammate_roster_states'] == {'same_team_other_roster_status':1}
    assert result['unidentified_week4_roster_rows'] == 1


def test_roster_audit_rejects_identity_ambiguity_and_missing_team_coverage():
    rows, injuries, contexts, forecasts = fixture()
    with pytest.raises(ValueError, match='duplicate'):
        roster.summarize(rows+[dict(rows[0])], injuries, contexts, forecasts)
    with pytest.raises(ValueError, match='team coverage'):
        roster.summarize([row for row in rows if row["team"] != "T01"], injuries, contexts, forecasts)
    with pytest.raises(ValueError, match='no forecast'):
        roster.summarize(rows, injuries, [dict(contexts[0], ticker='unknown')], forecasts)
