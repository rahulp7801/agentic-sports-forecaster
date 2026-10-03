"""Recent context is a dated subset, not a probability or absence inference."""
from copy import deepcopy
from datetime import date
import pytest
from sportsbet.prop.recent_participation import recent_participation

CUTOFF=date(2026,10,8)
GROUPS={'active':[(date(2025,10,1),100),(date(2026,9,7),90),
                  (date(2026,9,8),10),(date(2026,10,7),20)],
        'absent':[(date(2026,9,9),15.5)],'unknown':[(date(2026,10,1),1000)]}


def test_recent_window_excludes_old_games_includes_boundary_and_preserves_unknowns():
    before=deepcopy(GROUPS)
    r=recent_participation(GROUPS,CUTOFF,15.5,'over')
    assert r['since']=='2026-09-08' and r['cutoff']=='2026-10-08'
    assert r['active']==dict(games=2,mean=15.,hit_rate=.5)
    assert r['absent']==dict(games=1,mean=15.5,hit_rate=0.)
    assert r['unknown_games']==1
    assert r['sample_window']['active']==dict(oldest='2026-09-08',newest='2026-10-07')
    assert GROUPS==before


def test_old_history_and_missing_participation_cannot_invent_current_form():
    r=recent_participation(dict(active=[(date(2025,1,1),10)],absent=[],unknown=[(date(2026,10,7),50)]),CUTOFF,20,'under')
    assert r['active']==r['absent']==dict(games=0,mean=None,hit_rate=None)
    assert r['unknown_games']==1 and r['sample_window']['active'] is None


@pytest.mark.parametrize('day',[date(2026,10,8),date(2026,10,9),'2026-10-01'])
def test_target_day_or_future_rows_never_enter_recent_context(day):
    with pytest.raises(ValueError):recent_participation(dict(active=[(day,20)],absent=[],unknown=[]),CUTOFF,20,'under')


@pytest.mark.parametrize('value',[None,True,float('nan'),float('inf')])
def test_unobserved_or_invalid_values_do_not_become_zero(value):
    with pytest.raises(ValueError):recent_participation(dict(active=[(date(2026,10,7),value)],absent=[],unknown=[]),CUTOFF,20,'under')


def test_recorded_under_uses_exact_line_and_keeps_ties_in_original_denominator():
    r=recent_participation(GROUPS,CUTOFF,15.5,'under')
    assert r['active']['hit_rate']==.5 and r['absent']['hit_rate']==0


def test_calendar_window_crosses_seasons_without_changing_eligibility():
    r=recent_participation(dict(active=[(date(2025,12,20),10)],absent=[],unknown=[]),date(2026,1,2),5,'over')
    assert r['since']=='2025-12-03' and r['active']['games']==1
