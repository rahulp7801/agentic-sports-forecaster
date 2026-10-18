"""Atomic snapshot batches retain exact payloads and never retry failed writes."""
from copy import deepcopy
import json
from unittest.mock import Mock

import pytest

from sportsbet import dashboard


@pytest.mark.parametrize('batch', [
    None, {}, 'snapshot', iter([('one', {})]), [], (),
    [('one',)], [('one', {}, 'extra')], ['one'], [(True, {})], [('', {})],
    [('bad\x00key', {})], [('one', [])], [('one', None)], [('one', {}), ('one', {})],
    [(str(index), {}) for index in range(dashboard.MAX_SNAPSHOT_BATCH_SIZE + 1)],
])
def test_invalid_batch_rejects_before_creating_an_engine(monkeypatch, batch):
    factory = Mock()
    monkeypatch.setattr(dashboard, 'get_sync_engine', factory)
    with pytest.raises(ValueError, match='^Invalid snapshot batch$'):
        dashboard.publish_snapshots(batch)
    factory.assert_not_called()


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), object()])
def test_all_payloads_are_serialized_before_database_io(monkeypatch, bad):
    factory = Mock()
    monkeypatch.setattr(dashboard, 'get_sync_engine', factory)
    with pytest.raises((TypeError, ValueError)):
        dashboard.publish_snapshots([('first', {'captured_at': 'original'}), ('second', {'bad': bad})])
    factory.assert_not_called()


def test_success_uses_one_transaction_and_one_batch_with_exact_existing_json(monkeypatch):
    captured = '2026-10-18T18:53:07.610862+00:00'
    items = [('kalshi-props:nfl', {'captured_at': captured, 'label': 'café', 'rows': [1, 2]}),
             ('markets:nfl', {'captured_at': captured, 'execution_ready': False})]
    original = deepcopy(items)
    connection = Mock()
    engine = Mock()
    engine.begin.return_value.__enter__ = Mock(return_value=connection)
    engine.begin.return_value.__exit__ = Mock(return_value=False)
    factory = Mock(return_value=engine)
    monkeypatch.setattr(dashboard, 'get_sync_engine', factory)

    dashboard.publish_snapshots(items)

    factory.assert_called_once_with()
    engine.begin.assert_called_once_with()
    connection.execute.assert_called_once()
    statement, rows = connection.execute.call_args.args
    assert str(statement) == ('INSERT INTO dashboard_snapshots(snapshot_key,payload) VALUES (:key,CAST(:payload AS JSONB)) '
                              'ON CONFLICT(snapshot_key) DO UPDATE SET payload=excluded.payload,updated_at=NOW()')
    assert rows == [{'key': key, 'payload': json.dumps(payload, allow_nan=False)} for key, payload in original]
    assert [json.loads(row['payload'])['captured_at'] for row in rows] == [captured, captured]
    assert items == original
    engine.dispose.assert_called_once_with()


@pytest.mark.parametrize('where', ['begin', 'execute', 'commit_acknowledgement'])
def test_transaction_failures_propagate_once_and_always_dispose(monkeypatch, where):
    failure = RuntimeError('synthetic database failure')
    connection = Mock()
    engine = Mock()
    engine.begin.return_value.__enter__ = Mock(return_value=connection)
    engine.begin.return_value.__exit__ = Mock(return_value=False)
    if where == 'begin':
        engine.begin.side_effect = failure
    elif where == 'execute':
        connection.execute.side_effect = failure
    else:
        # Commit may have reached the server. Preserve uncertainty; do not
        # assume rollback or replay the batch when its acknowledgement fails.
        engine.begin.return_value.__exit__.side_effect = failure
    factory = Mock(return_value=engine)
    monkeypatch.setattr(dashboard, 'get_sync_engine', factory)

    with pytest.raises(RuntimeError) as raised:
        dashboard.publish_snapshots([('first', {}), ('second', {})])

    assert raised.value is failure
    factory.assert_called_once_with()
    engine.begin.assert_called_once_with()
    assert connection.execute.call_count == (0 if where == 'begin' else 1)
    if where == 'execute':
        assert engine.begin.return_value.__exit__.call_args.args[1] is failure
    elif where == 'commit_acknowledgement':
        assert engine.begin.return_value.__exit__.call_args.args == (None, None, None)
    engine.dispose.assert_called_once_with()
