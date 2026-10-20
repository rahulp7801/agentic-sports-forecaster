"""Synthetic SQLite checks for bounded live settlement snapshots and raw-state CAS."""
from contextlib import contextmanager
from datetime import datetime

import pytest

from sportsbet.live_settlement_ledger import Ledger
from tests.test_nba_settlement_identity import CAPTURED, payload, raw_state


@pytest.mark.parametrize('count', [250, 251])
def test_live_settlement_reads_payload_and_raw_state_once_per_bounded_batch(tmp_path, monkeypatch, count):
    ledger = Ledger(tmp_path/'batch.sqlite')
    values = [payload(line=index+.5) for index in range(count)]
    keys = ledger.record_many('batch', values)
    original_connect = ledger.connect
    calls = []

    @contextmanager
    def connection():
        with original_connect() as db:
            class Proxy:
                def execute(self, sql, args=()):
                    calls.append((sql, tuple(args)))
                    return db.execute(sql, args)
            yield Proxy()

    monkeypatch.setattr(ledger, 'connect', connection)
    ledger.settle(dict.fromkeys(keys, True), source='manual',
        observed_at=datetime.fromisoformat(CAPTURED))

    reads = [(sql, args) for sql, args in calls if sql.startswith('SELECT ')]
    assert [len(args) for _, args in reads] == ([250] if count == 250 else [250, 1])
    assert all(sql.startswith('SELECT id,payload,outcome,outcome_source,outcome_ref,')
        and 'outcome_observed_at,actual_value,outcome_evidence' in sql for sql, _ in reads)
    assert all(len(args) <= 250 for _, args in reads)
    assert len([sql for sql, _ in calls if sql.startswith('UPDATE predictions')]) == count
    with original_connect() as db:
        rows = db.execute('SELECT id,outcome,outcome_source,outcome_ref,outcome_observed_at,'
            'actual_value,outcome_evidence FROM predictions').fetchall()
    assert len(rows) == count and {row[0] for row in rows} == set(keys)
    assert all(row[1:] == ('true', 'manual', 'caller_supplied', CAPTURED, None, None) for row in rows)


@pytest.mark.parametrize('column, changed', [
    ('outcome', 'false'), ('outcome_source', 'manual'), ('outcome_ref', 'concurrent'),
    ('outcome_observed_at', CAPTURED), ('actual_value', 17), ('outcome_evidence', '{}'),
])
def test_each_stale_raw_field_blocks_cas_and_rolls_back_the_other_update(
        tmp_path, monkeypatch, column, changed):
    ledger = Ledger(tmp_path/'race.sqlite')
    other, raced = ledger.record_many('race', [payload(line=19.5), payload()])
    original_connect = ledger.connect
    injected = False

    @contextmanager
    def connection():
        nonlocal injected
        with original_connect() as db:
            class Proxy:
                def execute(self, sql, args=()):
                    nonlocal injected
                    cursor = db.execute(sql, args)
                    if sql.startswith('SELECT id,payload,outcome,outcome_source,outcome_ref,') and not injected:
                        retained = cursor.fetchall()
                        injected = True
                        with original_connect() as concurrent:
                            # Column is restricted to this fixed synthetic parameter list.
                            concurrent.execute(f'UPDATE predictions SET {column}=? WHERE id=?', (changed, raced))
                        class Snapshot:
                            def fetchall(self): return retained
                        return Snapshot()
                    return cursor
            yield Proxy()

    monkeypatch.setattr(ledger, 'connect', connection)
    with pytest.raises(ValueError, match='prior state changed'):
        ledger.settle({other: True, raced: True}, source='manual')
    expected = [None]*6
    columns = ('outcome', 'outcome_source', 'outcome_ref', 'outcome_observed_at', 'actual_value', 'outcome_evidence')
    expected[columns.index(column)] = changed
    assert injected and raw_state(ledger, raced) == tuple(expected)
    assert raw_state(ledger, other) == (None,)*6
