"""Offline slate diagnostics preserve failure, cache and receipt semantics."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from types import SimpleNamespace
import sys
from unittest.mock import AsyncMock, Mock

import httpx
import psycopg
from psycopg.errors import ConnectionFailure
import pytest
import requests
import sqlalchemy
from sqlalchemy.exc import OperationalError

from sportsbet import dashboard, diagnostics, schedules


NOW = datetime(2026, 10, 21, 16, tzinfo=timezone.utc)
CAPTURE = '2026-10-21T11:59:55.123456-04:00'
ORIGINAL_COLLECT = schedules.collect


@pytest.fixture(autouse=True)
def prohibit_external_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('External I/O is forbidden in slate diagnostic regressions')

    monkeypatch.setattr(httpx.Client, 'send', forbidden)
    monkeypatch.setattr(httpx.AsyncClient, 'send', forbidden)
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
    monkeypatch.setattr(psycopg, 'connect', forbidden)
    monkeypatch.setattr(sqlalchemy, 'create_engine', forbidden)


@pytest.fixture
def slate(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    original = dict(sport='cfb', captured_at=CAPTURE, as_of_date='2026-10-21',
                    status='complete', partial=False, games=[], failures=[], sources=['espn'])
    state = SimpleNamespace(original=original, read=Mock(return_value=None),
                            collect=AsyncMock(return_value=original), publish=Mock())
    monkeypatch.setattr(schedules, 'datetime', Clock)
    monkeypatch.setattr(schedules, 'collect', state.collect)
    monkeypatch.setattr(dashboard, 'load_snapshot', state.read)
    monkeypatch.setattr(dashboard, 'publish_snapshot', state.publish)
    return state


def private_failure():
    failure = OperationalError('SELECT PRIVATE_SQL', {'key': 'PRIVATE_PARAMETER'},
                               ConnectionFailure('postgres://PRIVATE_PASSWORD@private.invalid/PRIVATE_BODY'))
    failure.add_note('PRIVATE_NOTE')
    return failure


def record(stage, error_type='OperationalError', sqlstate='08006'):
    value = dict(schema_version=1, diagnostic_kind='operation_failure',
                 operation='slate_publication', stage=stage, error_type=error_type)
    if sqlstate is not None:
        value['sqlstate'] = sqlstate
    return value


def diagnostics_from(capsys):
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'PRIVATE_' not in captured.err and 'private.invalid' not in captured.err
    return [json.loads(line) for line in captured.err.splitlines()]


def inject_failure(slate, phase, failure):
    if phase == 'cache_read':
        slate.read.side_effect = failure
    elif phase == 'collection':
        slate.collect.side_effect = failure
    elif phase == 'projection':
        class UnprojectableGame(dict):
            def __getitem__(self, key):
                if key == 'game_time':
                    raise failure
                return super().__getitem__(key)
        slate.original['games'] = [UnprojectableGame(completed=False, provider_event_id='123')]
    elif phase == 'publication':
        slate.publish.side_effect = failure


@pytest.mark.asyncio
async def test_unsupported_sport_is_diagnosed_before_receipt_or_io(slate, capsys):
    receipt = {'original': 'retained'}
    with pytest.raises(ValueError, match='^Unsupported sport$') as raised:
        await schedules.publish_slate('unsupported', NOW, receipt=receipt)
    assert type(raised.value) is ValueError and receipt == {'original': 'retained'}
    slate.read.assert_not_called()
    slate.collect.assert_not_awaited()
    slate.publish.assert_not_called()
    assert diagnostics_from(capsys) == [record('arguments', 'ValueError', None)]


@pytest.mark.asyncio
async def test_initialization_failure_preserves_same_error_without_source_requests(slate, capsys):
    failure = private_failure()
    class BrokenReceipt(dict):
        def clear(self):
            raise failure
    with pytest.raises(OperationalError) as raised:
        await schedules.publish_slate('cfb', NOW, receipt=BrokenReceipt())
    assert raised.value is failure
    slate.read.assert_not_called()
    slate.collect.assert_not_awaited()
    slate.publish.assert_not_called()
    assert diagnostics_from(capsys) == [record('initialize')]


@pytest.mark.asyncio
@pytest.mark.parametrize('phase', ['cache_read', 'collection', 'projection', 'publication'])
async def test_terminal_phase_preserves_exception_and_never_creates_capture_receipt(slate, phase, capsys):
    failure = private_failure()
    inject_failure(slate, phase, failure)
    receipt = {'captured_at': 'old-capture'}
    with pytest.raises(OperationalError) as raised:
        await schedules.publish_slate('cfb', NOW, receipt=receipt)
    assert raised.value is failure and failure.__notes__ == ['PRIVATE_NOTE']
    assert receipt == {}
    slate.read.assert_called_once_with('slate:cfb')
    assert slate.collect.await_count == (0 if phase == 'cache_read' else 1)
    assert slate.publish.call_count == (1 if phase == 'publication' else 0)
    assert diagnostics_from(capsys) == [record(phase)]


@pytest.mark.asyncio
@pytest.mark.parametrize('previous', [{}, {'captured_at': 'PRIVATE_BAD_CLOCK'},
    {'captured_at': '2026-10-21T16:00:00', 'as_of_date': '2026-10-21', 'status': 'complete'},
    {'captured_at': '2026-10-21T16:00:01+00:00', 'as_of_date': '2026-10-21', 'status': 'complete'}])
async def test_expected_cache_parse_and_age_misses_are_silent(slate, previous, capsys):
    slate.read.return_value = previous
    receipt = {}
    assert await schedules.publish_slate('cfb', NOW, receipt=receipt) == 'complete'
    slate.collect.assert_awaited_once_with('cfb', NOW, offsets=tuple(range(7)))
    slate.publish.assert_called_once()
    assert receipt == {'captured_at': CAPTURE}
    assert diagnostics_from(capsys) == []


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['complete', 'partial'])
async def test_cache_hit_keeps_original_offset_clock_without_collection_or_write(slate, status, capsys):
    slate.read.return_value = dict(slate.original, status=status, partial=status == 'partial')
    receipt = {}
    assert await schedules.publish_slate('cfb', NOW, receipt=receipt) == 'cached'
    assert receipt == {'captured_at': CAPTURE}
    slate.collect.assert_not_awaited()
    slate.publish.assert_not_called()
    assert diagnostics_from(capsys) == []


@pytest.mark.asyncio
async def test_projection_still_bounds_sorts_and_filters_without_changing_capture(slate, capsys):
    games = [dict(completed=False, game_time='2026-10-22T12:00:00+00:00', provider_event_id=str(i).zfill(3))
             for i in reversed(range(101))]
    slate.original['games'] = games + [dict(completed=True)]
    original = deepcopy(slate.original)
    receipt = {}
    assert await schedules.publish_slate('cfb', NOW, receipt=receipt) == 'partial'
    published = slate.publish.call_args.args[1]
    assert len(published['games']) == 100 and published['games'][0]['provider_event_id'] == '000'
    assert published['status'] == 'partial' and published['partial'] is True
    assert published['captured_at'] == CAPTURE and receipt == {'captured_at': CAPTURE}
    assert slate.original == original
    slate.publish.assert_called_once()
    assert diagnostics_from(capsys) == []


@pytest.mark.asyncio
async def test_recovered_per_date_collection_failure_is_not_a_terminal_diagnostic(slate, monkeypatch, capsys):
    response = Mock()
    response.json.return_value = {}
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.side_effect = [RuntimeError('PRIVATE_RECOVERED_PROVIDER_BODY'), response]
    monkeypatch.setattr(schedules.httpx, 'AsyncClient', lambda **kwargs: client)
    monkeypatch.setattr(schedules, 'parse_day', Mock(return_value=[]))
    result = await ORIGINAL_COLLECT('cfb', NOW, offsets=(0, 1))
    assert result['status'] == 'partial' and result['partial'] is True
    assert result['failures'] == [{'date': '20261021', 'error_type': 'RuntimeError'}]
    assert client.get.await_count == 2 and len(result['sources']) == 1
    assert diagnostics_from(capsys) == []


@pytest.mark.parametrize('phase', ['cache_read', 'collection', 'projection', 'publication'])
def test_cli_reports_precise_phase_then_aggregate_without_retry(slate, phase, monkeypatch, tmp_path, capsys):
    failure = private_failure()
    inject_failure(slate, phase, failure)
    output = tmp_path / 'receipt.json'
    monkeypatch.setattr(sys, 'argv', ['schedules', '--sport', 'cfb', '--report-output', str(output)])
    with pytest.raises(SystemExit) as raised:
        schedules.main()
    assert raised.value.code == 'Schedule publication unavailable (OperationalError)'
    assert diagnostics_from(capsys) == [record(phase), record('publish')]
    assert slate.read.call_count == 1
    assert slate.collect.await_count == (0 if phase == 'cache_read' else 1)
    assert slate.publish.call_count == (1 if phase == 'publication' else 0)
    assert not output.exists() and not output.with_name('receipt.json.tmp').exists()


@pytest.mark.parametrize('status', ['complete', 'partial', 'cached', 'unavailable'])
def test_cli_normal_states_keep_original_output_exit_and_receipt(slate, status, monkeypatch, tmp_path, capsys):
    if status == 'cached':
        slate.read.return_value = slate.original
    else:
        slate.original.update(status=status, partial=status != 'complete')
    output = tmp_path / 'nested' / 'receipt.json'
    monkeypatch.setattr(sys, 'argv', ['schedules', '--sport', 'cfb', '--report-output', str(output)])
    if status == 'unavailable':
        with pytest.raises(SystemExit) as raised:
            schedules.main()
        assert raised.value.code == 2 and not output.exists()
        slate.publish.assert_not_called()
    else:
        schedules.main()
        assert json.loads(output.read_text()) == {'slates': {'cfb': {'captured_at': CAPTURE}}}
        assert not output.with_name('receipt.json.tmp').exists()
    captured = capsys.readouterr()
    assert captured.out == status + '\n' and captured.err == ''
    assert slate.collect.await_count == (0 if status == 'cached' else 1)


def test_cli_receipt_write_failure_has_only_its_own_phase(slate, monkeypatch, tmp_path, capsys):
    failure = OSError('PRIVATE_RECEIPT_PATH')
    monkeypatch.setattr(schedules, '_write_slate_receipt', Mock(side_effect=failure))
    output = tmp_path / 'receipt.json'
    monkeypatch.setattr(sys, 'argv', ['schedules', '--sport', 'cfb', '--report-output', str(output)])
    with pytest.raises(SystemExit) as raised:
        schedules.main()
    assert raised.value.code == 'Schedule publication unavailable (OSError)'
    slate.publish.assert_called_once()
    assert not output.exists()
    assert diagnostics_from(capsys) == [record('receipt_write', 'OSError', None)]


def test_cli_invalid_status_does_not_echo_the_untrusted_value(slate, monkeypatch, capsys):
    publish = AsyncMock(return_value='PRIVATE_UNKNOWN_STATUS')
    monkeypatch.setattr(schedules, 'publish_slate', publish)
    monkeypatch.setattr(sys, 'argv', ['schedules', '--sport', 'cfb'])
    with pytest.raises(SystemExit) as raised:
        schedules.main()
    assert raised.value.code == 'Schedule publication unavailable (ValueError)'
    publish.assert_awaited_once_with('cfb')
    assert diagnostics_from(capsys) == [record('status', 'ValueError', None)]


def test_cli_output_failure_does_not_claim_publication_failed(slate, monkeypatch, capsys):
    monkeypatch.setattr(schedules, 'print', Mock(side_effect=OSError('PRIVATE_OUTPUT_FAILURE')), raising=False)
    monkeypatch.setattr(sys, 'argv', ['schedules', '--sport', 'cfb'])
    with pytest.raises(SystemExit) as raised:
        schedules.main()
    assert raised.value.code == 'Schedule publication unavailable (OSError)'
    slate.publish.assert_called_once()
    assert diagnostics_from(capsys) == [record('output', 'OSError', None)]


@pytest.mark.asyncio
async def test_broken_diagnostic_stream_cannot_replace_original_publication_error(slate, monkeypatch):
    class BrokenStream:
        def write(self, value):
            raise OSError('PRIVATE_STREAM_FAILURE')
    failure = private_failure()
    slate.publish.side_effect = failure
    monkeypatch.setattr(diagnostics.sys, 'stderr', BrokenStream())
    receipt = {}
    with pytest.raises(OperationalError) as raised:
        await schedules.publish_slate('cfb', NOW, receipt=receipt)
    assert raised.value is failure and receipt == {}
    slate.publish.assert_called_once()


def test_new_diagnostic_scope_rejects_unbounded_stages():
    for stage in ('PRIVATE_URL', 'cache_read\nPRIVATE_NOTE', True, None):
        with pytest.raises(ValueError, match='^Invalid failure diagnostic scope$'):
            diagnostics.failure_record(RuntimeError('PRIVATE_BODY'), operation='slate_publication', stage=stage)
