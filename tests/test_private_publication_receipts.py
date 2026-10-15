import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('receipt_verifier',Path('.github/scripts/verify-published-snapshots.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def test_exact_publication_receipts_remain_private_and_use_parameterized_snapshot_keys():
    at='2026-10-06T20:00:00+00:00'
    report={'markets':{'nfl':{'captured_at':at}},'schedules':{'nba':{'captured_at':at}}}
    seen=[]
    def read(key):seen.append(key);return {'captured_at':at}
    assert module.verify_captures(report,read)==2
    assert seen==['markets:nfl','schedule:nba']
    with pytest.raises(ValueError,match='does not match'):
        module.verify_captures(report,lambda key:{'captured_at':'2026-10-05T20:00:00+00:00'})
    for bad in ({},{'markets':{'nfl':{'captured_at':'invalid'}}},{'markets':{'nfl':{'captured_at':'2026-10-06T20:00:00'}}}):
        with pytest.raises(ValueError):module.receipt_entries(bad)


def test_cfb_slate_receipt_verifies_the_slate_including_a_cached_original_capture():
    at='2026-10-15T09:00:00+00:00'
    report={'slates':{'cfb':{'captured_at':at}}}
    seen=[]
    def read(key):
        seen.append(key)
        return {'captured_at':at}
    assert module.verify_captures(report,read)==1
    assert seen==['slate:cfb']


@pytest.mark.parametrize('cfb_row',[None,{}, {'captured_at':'2026-10-14T09:00:00+00:00'}])
def test_matching_nfl_nba_receipts_cannot_hide_a_missing_or_stale_cfb_slate(cfb_row):
    at='2026-10-15T09:00:00+00:00'
    report={category:{sport:{'captured_at':at} for sport in ('nfl','nba')}
            for category in ('markets','schedules')}
    report['slates']={'cfb':{'captured_at':at}}
    stored={key:{'captured_at':at} for key in ('markets:nfl','schedule:nfl','markets:nba','schedule:nba')}
    # The separate schedule key is not proof that the consumer's slate was written.
    stored['schedule:cfb']={'captured_at':at}
    stored['slate:cfb']=cfb_row
    with pytest.raises(ValueError,match='slate:cfb: published capture does not match this run'):
        module.verify_captures(report,stored.get)
    stored['slate:cfb']={'captured_at':at}
    assert module.verify_captures(report,stored.get)==5


@pytest.mark.parametrize('captured',['invalid','2026-10-15T09:00:00',123])
def test_invalid_cfb_slate_receipts_fail_before_database_reads(captured):
    def read(key):
        pytest.fail('Invalid receipt must be rejected before reading snapshots')
    with pytest.raises(ValueError):
        module.verify_captures({'slates':{'cfb':{'captured_at':captured}}},read)


def test_real_cfb_cli_receipt_matches_the_original_consumer_slate(monkeypatch,tmp_path):
    import json
    import sys
    from unittest.mock import AsyncMock
    from sportsbet import schedules

    captured='2026-10-15T09:00:00.123456+00:00'
    stored={}
    reads=[]
    collect=AsyncMock(return_value={
        'sport':'cfb','captured_at':captured,'as_of_date':'2026-10-15',
        'status':'complete','partial':False,'games':[],
        'sources':['fixture-source-not-part-of-receipt'],'failures':[]})
    def load(key):
        reads.append(key)
        return None
    monkeypatch.setattr(schedules,'collect',collect)
    monkeypatch.setattr('sportsbet.dashboard.load_snapshot',load)
    monkeypatch.setattr('sportsbet.dashboard.publish_snapshot',lambda key,value:stored.update({key:value}))
    output=tmp_path/'cfb-slate-report.json'
    monkeypatch.setattr(sys,'argv',['schedules','--sport','cfb','--report-output',str(output)])

    schedules.main()

    report=json.loads(output.read_text(encoding='utf-8'))
    assert report=={'slates':{'cfb':{'captured_at':captured}}}
    assert reads==['slate:cfb'] and collect.await_count==1
    assert stored['slate:cfb']['captured_at']==captured
    assert module.verify_captures(report,stored.get)==1
    stored['slate:cfb']['captured_at']='2026-10-14T09:00:00.123456+00:00'
    with pytest.raises(ValueError,match='slate:cfb: published capture does not match this run'):
        module.verify_captures(report,stored.get)
