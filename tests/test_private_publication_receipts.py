import importlib.util
from pathlib import Path
import pytest
import json
from types import SimpleNamespace
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


@pytest.mark.parametrize('fault,expected_stage',[('connect','connect'),('read','snapshot_read'),
                                               ('mismatch','verify'),('close','close'),(None,None)])
def test_receipt_main_distinguishes_connection_read_mismatch_and_success(monkeypatch,tmp_path,capsys,fault,expected_stage):
    from psycopg.errors import ConnectionFailure
    from sqlalchemy.exc import OperationalError
    captured='2026-10-18T17:02:34.123456+00:00'
    receipt=tmp_path/'receipt.json'
    receipt.write_text(json.dumps({'slates':{'cfb':{'captured_at':captured}}}),encoding='utf-8')
    failure=OperationalError('SELECT private_sql',{},ConnectionFailure('postgres://private_credential'))
    calls=[]
    class Connection:
        def __enter__(self):
            return self
        def __exit__(self,*args):
            if fault=='close':raise failure
        def execute(self,sql,params):
            calls.append(('read',sql,params))
            if fault=='read':raise failure
            value='2026-10-17T17:02:34.123456+00:00' if fault=='mismatch' else captured
            return SimpleNamespace(fetchone=lambda:({'captured_at':value},))
    def connect(dsn,**kwargs):
        calls.append(('connect',dsn,kwargs))
        if fault=='connect':raise failure
        return Connection()
    loader=SimpleNamespace(exec_module=lambda target:None)
    monkeypatch.setattr(module.importlib.util,'spec_from_file_location',lambda *args:SimpleNamespace(loader=loader))
    monkeypatch.setattr(module.importlib.util,'module_from_spec',lambda spec:SimpleNamespace(hosted_read_dsn=lambda value:'private_dsn_fixture'))
    monkeypatch.setattr(module.psycopg,'connect',connect)
    monkeypatch.setenv('PUBLIC_DATA_REPORT_PATH',str(receipt))
    monkeypatch.setenv('DATABASE_URL','private_config_fixture')
    if fault:
        with pytest.raises(ValueError if fault=='mismatch' else OperationalError) as raised:
            module.main()
        if fault!='mismatch':assert raised.value is failure
    else:
        module.main()
    assert calls[0]==('connect','private_dsn_fixture',{'connect_timeout':5,
        'options':'-c statement_timeout=5000 -c default_transaction_read_only=on'})
    assert len(calls)==(1 if fault=='connect' else 2)
    if len(calls)>1:
        assert calls[1]==('read','SELECT payload FROM public.dashboard_snapshots WHERE snapshot_key=%s',('slate:cfb',))
    output=capsys.readouterr()
    assert 'private_' not in output.out+output.err
    if fault:
        assert output.out==''
        expected={'schema_version':1,'diagnostic_kind':'operation_failure',
            'operation':'published_snapshot_receipt','stage':expected_stage,
            'error_type':'ValueError' if fault=='mismatch' else 'OperationalError'}
        if fault!='mismatch':expected['sqlstate']='08006'
        assert json.loads(output.err)==expected
    else:
        assert json.loads(output.out)=={'verified_snapshot_receipts':1} and output.err==''
