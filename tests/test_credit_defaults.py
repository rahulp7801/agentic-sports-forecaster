import importlib
import sys
from datetime import datetime, timedelta, timezone

import pytest

from sportsbet.config import DEFAULT_DAILY_CREDIT_LIMIT, settings
from sportsbet.ledger import Ledger
from sportsbet.credit_projection import next_rolling_credit_release


@pytest.mark.parametrize('module_name',['daily','scan','market_watch'])
@pytest.mark.parametrize('requested',[None,8])
def test_all_collector_commands_default_to_twenty_and_allow_lower_limits(monkeypatch,module_name,requested):
    module=importlib.import_module('sportsbet.'+module_name)
    seen=[]
    async def run(*args,**kwargs):
        seen.append(args[2] if module_name=='daily' else args[1])
        if module_name=='daily':return {'status':'complete'}
        if module_name=='scan':return {'nfl':{'status':'complete'}}
        return {'sources':{'sportsbook':{'status':'observed'}},'comparisons':[]},{}
    monkeypatch.setattr(module,'run',run)
    argv=[module_name,'--sport','nfl']
    if requested is not None:argv+=['--daily-credit-limit',str(requested)]
    monkeypatch.setattr(sys,'argv',argv)
    module.main()
    assert seen==[20 if requested is None else requested]
    assert DEFAULT_DAILY_CREDIT_LIMIT==20


def test_default_atomic_reservation_keeps_reserve_and_stops_at_twenty(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'odds_rolling_credit_limit',450)
    ledger=Ledger(tmp_path/'default-budget.sqlite')
    assert ledger.reserve_api_credits(12,holdback=8)
    assert ledger.reserve_api_credits_with_reason(1,holdback=8)==(False,'pregame_credit_reserve')
    assert ledger.reserve_api_credits(8)
    assert ledger.reserve_api_credits_with_reason(1)==(False,'daily_credit_limit')
    with ledger.connect() as db:
        assert db.execute('SELECT SUM(credits) FROM api_usage').fetchone()[0]==20


def test_rolling_projection_reads_existing_usage_without_reserving_or_raising_caps(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'odds_rolling_credit_limit', 10)
    ledger = Ledger(tmp_path/'projection.sqlite')
    now = datetime(2026, 10, 3, 15, tzinfo=timezone.utc)
    with ledger.connect() as db:
        db.execute('INSERT INTO api_usage VALUES (?,?)', ((now.date()-timedelta(days=30)).isoformat(), 6))
        db.execute('INSERT INTO api_usage VALUES (?,?)', ((now.date()-timedelta(days=29)).isoformat(), 4))
    assert next_rolling_credit_release(ledger,4, now=now) == datetime(2026, 10, 4, tzinfo=timezone.utc)
    with ledger.connect() as db:
        assert db.execute('SELECT SUM(credits) FROM api_usage').fetchone()[0] == 10
    assert next_rolling_credit_release(ledger,11, now=now) is None
    assert next_rolling_credit_release(ledger,True, now=now) is None
    assert next_rolling_credit_release(ledger,0, now=now) is None


def test_rolling_projection_waits_for_enough_expiry_and_rejects_naive_clock(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'odds_rolling_credit_limit', 10)
    ledger = Ledger(tmp_path/'projection-two.sqlite')
    now = datetime(2026, 10, 3, 15, tzinfo=timezone.utc)
    with ledger.connect() as db:
        db.execute('INSERT INTO api_usage VALUES (?,?)', ((now.date()-timedelta(days=30)).isoformat(), 2))
        db.execute('INSERT INTO api_usage VALUES (?,?)', ((now.date()-timedelta(days=29)).isoformat(), 8))
    assert next_rolling_credit_release(ledger,4, now=now) == datetime(2026, 10, 5, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match='aware clock'):
        next_rolling_credit_release(ledger,4, now=now.replace(tzinfo=None))
