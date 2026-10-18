from datetime import datetime, timezone
from pathlib import Path
import json

import pytest

from sportsbet import cfb_public_settlement as worker

NOW = datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc)
PUBLIC_WORKFLOW = Path(__file__).parents[1] / '.github' / 'workflows' / 'public-data.yml'


@pytest.mark.parametrize(('reasons','status','pending'), [
    ({}, 'complete', 0),
    ({'stat_not_found_or_ambiguous': 3}, 'degraded', 3),
    ({'stat_provenance_invalid': 1}, 'degraded', 1),
    ({'final_game_not_matched': 3}, 'complete', 0),
])
def test_free_cfb_settlement_refreshes_exact_final_sources_and_publishes(
        monkeypatch, reasons, status, pending):
    events = []
    monkeypatch.setattr(worker, 'refresh_history', lambda sport, day: events.append(('refresh', sport, day)) or {'status': 'complete'})
    class Ledger:
        def predictions(self):
            return [{'prediction_id': 'recorded'}]
        def report(self, *args, **kwargs):
            return {'model_version': kwargs['model_version'], 'sport': kwargs['sport']}
    monkeypatch.setattr(worker, 'Ledger', Ledger)
    monkeypatch.setattr(worker, 'pending_schedule_offsets', lambda ledger, sport, now: (-10, -9))
    async def schedule(sport, now, *, offsets):
        events.append(('schedule', sport, offsets))
        return {'status': 'complete', 'captured_at': now.isoformat(), 'games': []}
    monkeypatch.setattr(worker, 'collect_schedule', schedule)
    monkeypatch.setattr(worker, 'settle_final_props', lambda ledger, sport, schedule: events.append(('settle', sport)) or {'status': 'complete', 'pending': sum(reasons.values()), 'reasons': reasons})
    monkeypatch.setattr(worker, 'publish_snapshot', lambda key, value: events.append(('publish', key, value)))
    monkeypatch.setattr(worker, 'build_pick_board', lambda predictions, sport: {'sport': sport})
    monkeypatch.setattr(worker, 'publish_history_shadow', lambda predictions, sport, publish: events.append(('shadow', sport)))

    result = worker.run(NOW)
    assert result['status'] == status
    assert result['final_stat_evidence_pending'] == pending
    assert ('reason' in result) == (pending > 0)
    assert events[0] == ('refresh', 'cfb', NOW.date())
    assert events[1] == ('schedule', 'cfb', tuple(sorted(set(range(-7, 2)) | {-10, -9})))
    assert events[2] == ('settle', 'cfb')
    assert {'metrics:all:cfb', 'metrics:recommendations:cfb', 'picks:cfb', 'pipeline:public_cfb_settlement'} <= {
        event[1] for event in events if event[0] == 'publish'}
    assert events[-1][2]['execution_ready'] is False


def test_failed_history_never_fetches_schedule_or_grades(monkeypatch):
    events = []
    monkeypatch.setattr(worker, 'refresh_history', lambda sport, day: {'status': 'failed', 'error_type': 'Unavailable'})
    monkeypatch.setattr(worker, 'Ledger', lambda: events.append('ledger'))
    monkeypatch.setattr(worker, 'collect_schedule', lambda *args, **kwargs: events.append('schedule'))
    monkeypatch.setattr(worker, 'settle_final_props', lambda *args, **kwargs: events.append('settle'))
    monkeypatch.setattr(worker, 'publish_snapshot', lambda key, value: events.append((key, value)))

    result = worker.run(NOW)
    assert result['status'] == 'blocked'
    assert result['reason'] == 'history_refresh_unavailable'
    assert len(events) == 1 and events[0][0] == 'pipeline:public_cfb_settlement'


def test_public_workflow_runs_cfb_settlement_only_on_free_daily_scope():
    source = PUBLIC_WORKFLOW.read_text(encoding='utf-8')
    step = source.split('      - name: Settle CFB from free final sources\n', 1)[1].split('\n      - name:', 1)[0]
    assert "env.OPERATION == 'public_daily'" in step
    assert "env.SPORT == 'both' || env.SPORT == 'cfb'" in step
    assert 'python -m sportsbet.cfb_public_settlement' in step
    assert 'ODDS_API_KEY' not in source
    assert source.index('name: Update CFB schedule without consuming odds credits') < source.index('name: Settle CFB from free final sources')
    schedule = source.split('      - name: Update CFB schedule without consuming odds credits\n', 1)[1].split('\n      - name:', 1)[0]
    assert 'id: worker_config' in source and 'id: schema' in source
    for item in (schedule, step):
        assert "always() && !cancelled()" in item
        assert "steps.worker_config.outcome == 'success'" in item
        assert "steps.schema.outcome == 'success'" in item


@pytest.mark.parametrize('stage',['history','ledger','pending_offsets','schedules','settlement',
                                  'predictions','publications','report_publish'])
def test_cfb_failure_diagnostic_identifies_stage_without_changing_exception(monkeypatch,capsys,stage):
    from psycopg.errors import ConnectionFailure
    from sqlalchemy.exc import OperationalError
    failure=OperationalError('SELECT private_sql',{},ConnectionFailure('postgres://private_credential'))
    def fail(*args,**kwargs):
        raise failure
    class Ledger:
        def predictions(self):
            if stage=='predictions':fail()
            return []
        def report(self,*args,**kwargs):
            return {}
    monkeypatch.setattr(worker,'refresh_history',fail if stage=='history' else lambda *args:{'status':'complete'})
    monkeypatch.setattr(worker,'Ledger',fail if stage=='ledger' else Ledger)
    monkeypatch.setattr(worker,'pending_schedule_offsets',fail if stage=='pending_offsets' else lambda *args:())
    async def collect(*args,**kwargs):
        if stage=='schedules':fail()
        return {'status':'complete'}
    monkeypatch.setattr(worker,'collect_schedule',collect)
    monkeypatch.setattr(worker,'settle_final_props',fail if stage=='settlement' else lambda *args:{'status':'complete'})
    def publish(key,value):
        if (stage=='publications' and key=='metrics:all:cfb') or (
                stage=='report_publish' and key=='pipeline:public_cfb_settlement'):
            fail()
    monkeypatch.setattr(worker,'publish_snapshot',publish)
    monkeypatch.setattr(worker,'build_pick_board',lambda *args:{})
    monkeypatch.setattr(worker,'publish_history_shadow',lambda *args:None)
    with pytest.raises(OperationalError) as raised:
        worker.run(NOW)
    assert raised.value is failure
    captured=capsys.readouterr()
    assert captured.out=='' and 'private_' not in captured.err
    assert json.loads(captured.err)=={'schema_version':1,'diagnostic_kind':'operation_failure',
        'operation':'cfb_settlement','stage':stage,'error_type':'OperationalError','sqlstate':'08006'}
