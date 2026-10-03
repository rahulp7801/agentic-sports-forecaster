"""Supplemental teammate changes do not rewrite the original acute-set audit."""
from __future__ import annotations

import pytest

from sportsbet.quant import kalshi_stat_only_context_change as original
from sportsbet.quant import kalshi_stat_only_context_status_detail as detail


def fixture():
    injuries = [dict(season=2026,season_type='REG',week=4,team=f'T{i:02d}',
                     gsis_id=f'fill{i}',position='LB',report_status=None)
                for i in range(32)]
    acute = dict(season=2026,season_type='REG',week=4,team='T00',
                 gsis_id='teammate',position='WR',report_status='Out')
    roster = [dict(season=2026,week=4,game_type='REG',team=f'T{i:02d}',
                   gsis_id=f'fill{i}',status='ACT') for i in range(32)]
    contexts = [dict(ticker=f'FIXED-{i}',historical_team='T00',
                     high_probability=i<11) for i in range(70)]
    forecasts = [dict(ticker=f'FIXED-{i}',gsis_player_id=f'subject{i}')
                 for i in range(70)]
    return contexts,forecasts,injuries+[acute],roster


def test_out_to_doubtful_same_teammate_is_visible_without_changing_original_report():
    contexts,forecasts,old,roster=fixture()
    new=[dict(row,report_status='Doubtful') if row['gsis_id']=='teammate'
         else dict(row) for row in old]
    assert original.compare(contexts,forecasts,old,new,roster,roster)['all_changes_zero'] is True
    result=detail.compare(contexts,forecasts,old,new)
    assert result['all_candidates']['candidates']==70
    assert result['high_probability_candidates']['candidates']==11
    assert result['all_candidates']['acute_teammate_status_changed']==70
    assert result['high_probability_candidates']['acute_teammate_status_changed']==11
    assert result['distinct_affected_clubs']==1
    assert result['all_teammate_context_changes_zero'] is False


def test_questionable_and_position_changes_are_reported_but_never_reselect_candidates():
    contexts,forecasts,old,_=fixture()
    questionable=dict(old[-1],gsis_id='other',report_status='Questionable')
    with_questionable=old+[questionable]
    result=detail.compare(contexts,forecasts,with_questionable,old)
    assert result['all_candidates']['questionable_teammate_status_changed']==70
    assert result['all_candidates']['acute_teammate_status_changed']==0
    changed=[dict(row,position='RB') if row['gsis_id']=='teammate'
             else dict(row) for row in old]
    result=detail.compare(contexts,forecasts,old,changed)
    assert result['all_candidates']['skill_teammate_position_changed']==70
    assert result['all_candidates']['acute_teammate_status_changed']==0
    assert detail.compare(contexts,forecasts,old,old)['all_teammate_context_changes_zero'] is True
    with pytest.raises(ValueError,match='denominator'):
        detail.compare(contexts[:-1],forecasts,old,old)
