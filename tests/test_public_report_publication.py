"""Offline report retention must not attest an unconfirmed summary publication."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import AsyncMock, Mock

import httpx
import psycopg
from psycopg.errors import QueryCanceled
import pytest
import requests
import sqlalchemy
from sqlalchemy.exc import OperationalError

from sportsbet import daily
from sportsbet.quant import history_shadow_audit


ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 10, 21, 12, 5, tzinfo=timezone.utc)
START = NOW - timedelta(seconds=30)
MARKET_CLOCKS = {'nfl': '2026-10-21T12:01:00+00:00', 'nba': '2026-10-21T12:02:00+00:00'}
SCHEDULE_CLOCK = '2026-10-21T12:03:00+00:00'


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / '.github' / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load_script('publication_report_validator', 'validate-public-report.py')
receipt_verifier = load_script('publication_receipt_verifier', 'verify-published-snapshots.py')


@pytest.fixture(autouse=True)
def prohibit_external_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('External I/O is forbidden in report publication regressions')

    monkeypatch.setattr(httpx.Client, 'send', forbidden)
    monkeypatch.setattr(httpx.AsyncClient, 'send', forbidden)
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
    monkeypatch.setattr(psycopg, 'connect', forbidden)
    monkeypatch.setattr(sqlalchemy, 'create_engine', forbidden)


@pytest.fixture
def pipeline(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    control = SimpleNamespace(failure=None, persist_before_failure=False,
                              calls=[], snapshots={})

    def publish(key, payload):
        control.calls.append((key, deepcopy(payload)))
        if key.startswith('pipeline:') and control.failure is not None:
            if control.persist_before_failure:
                control.snapshots[key] = deepcopy(payload)
            raise control.failure
        control.snapshots[key] = deepcopy(payload)

    async def watch(sport, *args, **kwargs):
        prizepicks = kwargs.get('provider') == 'public'
        summary = dict(captured_at=MARKET_CLOCKS[sport], sources={
            'sportsbook': dict(status='not_requested', partial_coverage=True),
            'kalshi': dict(status='observed', partial_coverage=False),
            'prizepicks': dict(status='observed' if prizepicks else 'not_requested',
                              partial_coverage=not prizepicks)})
        # The real watcher publishes this component before returning its capture.
        publish('markets:' + sport, summary)
        return summary, None

    async def collect(*args, **kwargs):
        return dict(status='complete', captured_at=SCHEDULE_CLOCK,
                    games=[], sources=[], failures=[])

    async def profiles(sports, **kwargs):
        assert kwargs['expected_public_captures'] == {
            sport: dict(market_captured_at=MARKET_CLOCKS[sport], slate_captured_at=SCHEDULE_CLOCK)
            for sport in sports}
        return {sport: dict(profiles=1, unavailable=0, signal_identities=0, public_identities=1,
                            public_input_status='observed', selected_events=1, selected_players=1)
                for sport in sports}

    class Ledger:
        def report(self, *args, **kwargs):
            return {'status': 'complete'}

        def predictions(self):
            return []

    monkeypatch.setattr(daily, 'datetime', Clock)
    monkeypatch.setattr(daily, 'PROFILE_READY_TIMEOUT_SECONDS', 1)
    monkeypatch.setattr(daily, 'publish_snapshot', publish)
    monkeypatch.setattr(daily, 'load_snapshot', lambda key: None if key.startswith('markets:') else
                        dict(status='complete', finished_at=NOW.isoformat()))
    monkeypatch.setattr(daily, 'watch', AsyncMock(side_effect=watch))
    monkeypatch.setattr(daily, 'collect_schedule', AsyncMock(side_effect=collect))
    monkeypatch.setattr(daily, 'refresh_history', Mock(return_value=dict(status='complete')))
    monkeypatch.setattr(daily, 'refresh_profiles', AsyncMock(side_effect=profiles))
    monkeypatch.setattr(daily, 'pending_schedule_offsets', Mock(return_value=()))
    monkeypatch.setattr(daily, 'settle_final_props', Mock(return_value=dict(status='complete',
                        candidates=0, settled=0, pending=0, execution_ready=False)))
    monkeypatch.setattr(daily, 'Ledger', Ledger)
    monkeypatch.setattr(daily, 'build_pick_board', Mock(return_value={}))
    monkeypatch.setattr(history_shadow_audit, 'publish_history_shadow', Mock())
    monkeypatch.setattr(daily, 'scan', AsyncMock(return_value={'nba': dict(status='complete')}))
    return control


def publication_error():
    error = OperationalError('SELECT PRIVATE_SQL FROM private_table', {'private_key': 'PRIVATE_PARAMETER'},
                             QueryCanceled('postgres://PRIVATE_CREDENTIAL@private.invalid/PRIVATE_BODY'))
    error.add_note('PRIVATE_NOTE')
    return error


def expected_diagnostic():
    return dict(schema_version=1, diagnostic_kind='operation_failure', operation='daily',
                stage='report', error_type='OperationalError', sqlstate='57014')


def validate(path, mode='public_monitor', producer_status=2):
    return validator.validate_report(path, mode=mode, sport='both', producer_status=producer_status,
                                     started_at=START.isoformat(), now=NOW)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['public_monitor', 'public_daily'])
@pytest.mark.parametrize('persisted', [False, True])
async def test_failed_public_summary_retains_original_components_without_attesting_commit(
        pipeline, mode, persisted, tmp_path, capsys):
    pipeline.failure = publication_error()
    pipeline.persist_before_failure = persisted
    report = await daily.run(['nfl', 'nba'], mode, 20)
    attempted = [payload for key, payload in pipeline.calls if key == 'pipeline:' + mode]
    assert len(attempted) == 1  # No collection or publication retry, including ambiguous commit outcomes.
    assert attempted[0]['status'] == 'observed' and 'report_publication' not in attempted[0]
    assert report == dict(attempted[0], status='degraded', report_publication=dict(
        status='failed', error_type='OperationalError', sqlstate='57014'))
    assert report['execution_ready'] is False and report['finished_at'] == NOW.isoformat()
    assert all(report['markets'][sport]['captured_at'] == clock for sport, clock in MARKET_CLOCKS.items())
    assert all(report['schedules'][sport]['captured_at'] == SCHEDULE_CLOCK for sport in MARKET_CLOCKS)
    assert daily.watch.await_count == 2
    assert ('pipeline:' + mode in pipeline.snapshots) is persisted
    if persisted:
        # An exception after possible commit does not prove rollback or permit a compensating rewrite.
        assert pipeline.snapshots['pipeline:' + mode] == attempted[0]
    output = tmp_path / 'report.json'
    daily._write_report(str(output), report)
    assert validate(output, mode) == {'validated_public_report_receipts': 4}
    seen = []

    def read(key):
        seen.append(key)
        return pipeline.snapshots.get(key)

    assert receipt_verifier.verify_captures(report, read) == 4
    assert seen == ['markets:nfl', 'schedule:nfl', 'markets:nba', 'schedule:nba']
    captured = capsys.readouterr()
    assert captured.out == '' and json.loads(captured.err) == expected_diagnostic()
    combined = json.dumps(report) + output.read_text() + captured.err
    assert 'PRIVATE_' not in combined and 'private.invalid' not in combined
    assert pipeline.failure.__notes__ == ['PRIVATE_NOTE']


@pytest.mark.parametrize('mode', ['public_monitor', 'public_daily'])
def test_actual_cli_writes_retained_report_before_degraded_exit(pipeline, mode, monkeypatch, tmp_path, capsys):
    pipeline.failure = publication_error()
    output = tmp_path / 'current' / 'report.json'
    monkeypatch.setattr(sys, 'argv', ['daily', '--sport', 'both', '--mode', mode,
                                     '--report-output', str(output)])
    with pytest.raises(SystemExit) as raised:
        daily.main()
    assert raised.value.code == 2
    captured = capsys.readouterr()
    printed = json.loads(captured.out)
    assert json.loads(output.read_text()) == printed
    assert printed['report_publication'] == dict(status='failed', error_type='OperationalError', sqlstate='57014')
    assert validate(output, mode) == {'validated_public_report_receipts': 4}
    assert json.loads(captured.err) == expected_diagnostic()
    assert len([key for key, _ in pipeline.calls if key == 'pipeline:' + mode]) == 1
    assert daily.watch.await_count == 2 and not output.with_name('report.json.tmp').exists()
    assert 'PRIVATE_' not in captured.out + captured.err


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['public_monitor', 'public_daily'])
async def test_successful_publication_keeps_original_report_shape(pipeline, mode, tmp_path, capsys):
    report = await daily.run(['nfl', 'nba'], mode, 20)
    assert set(report) == {'mode', 'finished_at', 'status', 'execution_ready', 'scope',
                           'histories', 'markets', 'schedules', 'settlements', 'props', 'profiles'}
    assert report['status'] == 'observed' and report == pipeline.snapshots['pipeline:' + mode]
    output = tmp_path / 'report.json'
    daily._write_report(str(output), report)
    assert validate(output, mode, producer_status=0) == {'validated_public_report_receipts': 4}
    assert len([key for key, _ in pipeline.calls if key == 'pipeline:' + mode]) == 1
    assert daily.watch.await_count == 2 and capsys.readouterr().err == ''


@pytest.mark.asyncio
async def test_nonpublic_summary_publication_failure_still_raises_same_error(pipeline, capsys):
    pipeline.failure = publication_error()
    with pytest.raises(OperationalError) as raised:
        await daily.run(['nba'], 'monitor', 20)
    assert raised.value is pipeline.failure
    assert len([key for key, _ in pipeline.calls if key == 'pipeline:monitor']) == 1
    assert json.loads(capsys.readouterr().err) == expected_diagnostic()


@pytest.mark.asyncio
async def test_report_construction_failure_is_not_recast_as_publication(pipeline, monkeypatch, capsys):
    monkeypatch.delitem(daily.PUBLIC_SCOPES, 'public_monitor')
    with pytest.raises(KeyError):
        await daily.run(['nfl', 'nba'], 'public_monitor', 20)
    assert not any(key.startswith('pipeline:') for key, _ in pipeline.calls)
    assert json.loads(capsys.readouterr().err) == dict(schema_version=1,
        diagnostic_kind='operation_failure', operation='daily', stage='report', error_type='KeyError')


def test_report_file_write_failure_remains_fatal_after_successful_publication(
        pipeline, monkeypatch, tmp_path, capsys):
    output = tmp_path / 'report.json'
    monkeypatch.setattr(sys, 'argv', ['daily', '--sport', 'both', '--mode', 'public_monitor',
                                     '--report-output', str(output)])
    failure = OSError('PRIVATE_LOCAL_PATH')
    monkeypatch.setattr(daily, '_write_report', Mock(side_effect=failure))
    with pytest.raises(SystemExit) as raised:
        daily.main()
    assert raised.value.code == 'Daily pipeline unavailable (OSError)'
    assert not output.exists()
    captured = capsys.readouterr()
    assert captured.out == '' and 'PRIVATE_' not in captured.err
    assert json.loads(captured.err) == dict(schema_version=1, diagnostic_kind='operation_failure',
        operation='daily', stage='report_write', error_type='OSError')
    assert len([key for key, _ in pipeline.calls if key == 'pipeline:public_monitor']) == 1


def retained_report():
    sports = ('nfl', 'nba')
    return dict(mode='public_monitor', finished_at=NOW.isoformat(), status='degraded', execution_ready=False,
        scope='Synthetic public observation; no source requests are made by these tests.',
        report_publication=dict(status='failed', error_type='OperationalError', sqlstate='57014'),
        histories={sport: dict(status='not_requested') for sport in sports},
        markets={sport: dict(status='observed', captured_at=MARKET_CLOCKS[sport]) for sport in sports},
        schedules={sport: dict(status='complete', captured_at=SCHEDULE_CLOCK,
                               slate_captured_at=SCHEDULE_CLOCK) for sport in sports},
        settlements={sport: dict(status='not_requested') for sport in sports},
        profiles={sport: dict(status='not_requested', reason='public_daily_only') for sport in sports},
        props={sport: dict(status='not_requested', reason='public_only_collection') for sport in sports})


def write_fixture(tmp_path, report):
    output = tmp_path / 'report.json'
    output.write_text(json.dumps(report), encoding='utf-8')
    return output


@pytest.mark.parametrize('metadata', [None, [], {}, 'failed', {'status': 'failed'},
    {'status': 'complete', 'error_type': 'OperationalError'},
    {'status': 'failed', 'error_type': 'private type'},
    {'status': 'failed', 'error_type': 'Érror'},
    {'status': 'failed', 'error_type': 'A' * 65},
    {'status': 'failed', 'error_type': ''},
    {'status': 'failed', 'error_type': True},
    {'status': 'failed', 'error_type': 'OperationalError', 'sqlstate': '57014 PRIVATE_SQL'},
    {'status': 'failed', 'error_type': 'OperationalError', 'sqlstate': 57014},
    {'status': 'failed', 'error_type': 'OperationalError', 'sqlstate': 'abcde'},
    {'status': 'failed', 'error_type': 'OperationalError', 'message': 'PRIVATE_BODY'},
    {'status': 'failed', 'error_type': 'OperationalError', 'published': True}])
def test_publication_metadata_cannot_widen_public_report_contract(tmp_path, metadata):
    report = retained_report()
    report['report_publication'] = metadata
    with pytest.raises(ValueError):
        validate(write_fixture(tmp_path, report))


@pytest.mark.parametrize('change', ['exit_zero', 'observed_exit_zero', 'observed_exit_two',
                                    'healthy_degraded_without_failure', 'execution_ready'])
def test_publication_failure_cannot_be_relabelled_healthy(tmp_path, change):
    report = retained_report()
    code = 2
    if change == 'exit_zero': code = 0
    elif change == 'observed_exit_zero': report['status'] = 'observed'; code = 0
    elif change == 'observed_exit_two': report['status'] = 'observed'
    elif change == 'healthy_degraded_without_failure': del report['report_publication']
    elif change == 'execution_ready': report['execution_ready'] = True
    with pytest.raises(ValueError):
        validate(write_fixture(tmp_path, report), producer_status=code)


@pytest.mark.parametrize('change', ['stale', 'future', 'capture_future', 'capture_naive',
                                    'capture_missing', 'failed_capture', 'slate_future'])
def test_failed_summary_publication_never_waives_source_chronology_or_receipt_rules(tmp_path, change):
    report = retained_report()
    if change == 'stale': report['finished_at'] = (START - timedelta(microseconds=1)).isoformat()
    elif change == 'future': report['finished_at'] = (NOW + timedelta(microseconds=1)).isoformat()
    elif change == 'capture_future': report['markets']['nfl']['captured_at'] = (NOW + timedelta(seconds=1)).isoformat()
    elif change == 'capture_naive': report['markets']['nfl']['captured_at'] = NOW.replace(tzinfo=None).isoformat()
    elif change == 'capture_missing': del report['markets']['nfl']['captured_at']
    elif change == 'failed_capture': report['markets']['nfl']['status'] = 'failed'
    elif change == 'slate_future': report['schedules']['nfl']['slate_captured_at'] = (NOW + timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError):
        validate(write_fixture(tmp_path, report))


def test_failed_component_still_has_no_fabricated_capture(tmp_path):
    report = retained_report()
    report['markets']['nba'] = dict(status='failed', error_type='OperationalError', sqlstate='57014')
    original = deepcopy(report)
    assert validate(write_fixture(tmp_path, report)) == {'validated_public_report_receipts': 3}
    assert report == original and 'captured_at' not in report['markets']['nba']
    assert receipt_verifier.receipt_entries(report) == [
        ('markets:nfl', MARKET_CLOCKS['nfl']), ('schedule:nfl', SCHEDULE_CLOCK),
        ('schedule:nba', SCHEDULE_CLOCK)]
