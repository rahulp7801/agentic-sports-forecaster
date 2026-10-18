from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
from unittest.mock import AsyncMock

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT/'.github/scripts/validate-public-report.py'
spec = importlib.util.spec_from_file_location('validate_public_report', SCRIPT)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
NOW = datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc)
START = NOW-timedelta(minutes=2)


def public_report(status='observed', mode='public_monitor', sports=('nfl', 'nba'), now=NOW):
    report = dict(mode=mode, finished_at=now.isoformat(), status=status, execution_ready=False,
        scope='Synthetic public-only observation; no quote collection in this test.',
        histories={sport:dict(status='complete' if mode == 'public_daily' else 'not_requested') for sport in sports},
        markets={sport:dict(status='observed', captured_at=(now-timedelta(minutes=3)).isoformat()) for sport in sports},
        schedules={sport:dict(status='complete', captured_at=(now-timedelta(days=1)).isoformat(),
            slate_captured_at=(now-timedelta(minutes=3)).isoformat()) for sport in sports},
        settlements={sport:dict(status='complete' if mode == 'public_daily' else 'not_requested') for sport in sports},
        profiles={sport:(dict(status='complete', profiles=1, unavailable=0, signal_identities=0,
            public_identities=1, public_input_status='observed', selected_events=1, selected_players=1)
            if mode == 'public_daily' else dict(status='not_requested', reason='public_daily_only')) for sport in sports},
        props={sport:dict(status='not_requested', reason='public_only_collection') for sport in sports})
    if status == 'degraded':
        report['markets'][sports[-1]] = dict(status='failed')
    return report


@pytest.fixture(autouse=True)
def no_database(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Report validation must not open a database')
    monkeypatch.setattr('psycopg.connect', forbidden)


@pytest.fixture
def report_path(tmp_path):
    path = tmp_path/'report.json'
    path.write_text(json.dumps(public_report()), encoding='utf-8')
    return path


def validate(path, **kwargs):
    options = dict(mode='public_monitor', sport='both', producer_status=0,
                   started_at=START.isoformat(), now=NOW)
    options.update(kwargs)
    return validator.validate_report(path, **options)


@pytest.mark.parametrize('mode', ['public_monitor', 'public_daily'])
@pytest.mark.parametrize('status,code', [('observed', 0), ('degraded', 2)])
def test_valid_current_report_includes_partial_and_cached_source_receipts(report_path, mode, status, code):
    report = public_report(status, mode)
    if status == 'degraded':
        report['markets']['nba'] = dict(status='failed')
    original = deepcopy(report)
    report_path.write_text(json.dumps(report), encoding='utf-8')
    assert validate(report_path, mode=mode, producer_status=code) == {
        'validated_public_report_receipts': 3 if status == 'degraded' else 4}
    assert json.loads(report_path.read_text(encoding='utf-8')) == original


@pytest.mark.parametrize('sport', ['nfl', 'nba'])
def test_exact_single_sport_scope_is_supported(report_path, sport):
    report_path.write_text(json.dumps(public_report(sports=(sport,))), encoding='utf-8')
    assert validate(report_path, sport=sport) == {'validated_public_report_receipts': 2}


@pytest.mark.parametrize('group,status', [('markets', 'observed'), ('markets', 'degraded'),
                                         ('schedules', 'complete')])
def test_published_component_cannot_silently_omit_its_receipt(report_path, group, status):
    report = public_report('degraded' if status == 'degraded' else 'observed')
    report[group]['nfl'] = dict(status=status)
    report_path.write_text(json.dumps(report), encoding='utf-8')
    with pytest.raises(ValueError): validate(report_path, producer_status=2 if status == 'degraded' else 0)


@pytest.mark.parametrize('group,status', [('markets', 'degraded'), ('schedules', 'partial'),
                                         ('histories', 'failed'), ('settlements', 'blocked'),
                                         ('profiles', 'degraded'), ('profiles', 'failed')])
def test_observed_status_cannot_contradict_daily_component_coverage(report_path, group, status):
    report = public_report(mode='public_daily')
    report[group]['nba']['status'] = status
    report_path.write_text(json.dumps(report), encoding='utf-8')
    with pytest.raises(ValueError): validate(report_path, mode='public_daily')


def test_real_degraded_market_retains_its_capture_receipt(report_path):
    report = public_report('degraded')
    report['markets']['nba'] = dict(status='degraded', captured_at=(NOW-timedelta(seconds=5)).isoformat())
    report_path.write_text(json.dumps(report), encoding='utf-8')
    assert validate(report_path, producer_status=2) == {'validated_public_report_receipts': 4}


@pytest.mark.parametrize('state', ['degraded', 'failed'])
def test_profile_failure_keeps_successful_market_receipts_and_degraded_exit(report_path, state):
    report=public_report(mode='public_daily')
    report['status']='degraded'
    report['profiles']['nba']=(dict(report['profiles']['nba'],status='degraded',public_input_status='rejected')
        if state=='degraded' else dict(status='failed',error_type='RuntimeError',sqlstate='08006'))
    report_path.write_text(json.dumps(report),encoding='utf-8')
    assert validate(report_path,mode='public_daily',producer_status=2)=={'validated_public_report_receipts':4}
    assert report['markets']['nba']['captured_at']==(NOW-timedelta(minutes=3)).isoformat()


@pytest.mark.parametrize('change', ['absent','extra_identity','bool_count','large_count','unknown_input',
    'masked_rejection','masked_unavailable','wrong_degraded','too_many_players','private_error',
    'invalid_error_type','invalid_sqlstate','monitor_request','slate_missing','slate_future'])
def test_profile_diagnostics_and_original_slate_clocks_are_bounded_and_required(report_path,change):
    report=public_report(mode='public_daily');mode='public_daily'
    value=report['profiles']['nba']
    if change=='absent': del report['profiles']
    elif change=='extra_identity': value['player']='RAW_PRIVATE_IDENTITY'
    elif change=='bool_count': value['profiles']=True
    elif change=='large_count': value['public_identities']=5001
    elif change=='unknown_input': value['public_input_status']='verified_by_guess'
    elif change=='masked_rejection': value['public_input_status']='rejected'
    elif change=='masked_unavailable': value.update(profiles=0,unavailable=1)
    elif change=='wrong_degraded': value['status']='degraded'
    elif change=='too_many_players': value['selected_players']=51
    elif change=='private_error': report['profiles']['nba']=dict(status='failed',error_type='RuntimeError',message='RAW_PRIVATE_REPORT')
    elif change=='invalid_error_type': report['profiles']['nba']=dict(status='failed',error_type='RAW PRIVATE REPORT')
    elif change=='invalid_sqlstate': report['profiles']['nba']=dict(status='failed',error_type='RuntimeError',sqlstate='url')
    elif change=='monitor_request':
        report=public_report();mode='public_monitor';report['profiles']['nba']=value
    elif change=='slate_missing': del report['schedules']['nba']['slate_captured_at']
    elif change=='slate_future': report['schedules']['nba']['slate_captured_at']=(NOW+timedelta(seconds=1)).isoformat()
    report_path.write_text(json.dumps(report),encoding='utf-8')
    with pytest.raises(ValueError): validate(report_path,mode=mode)


@pytest.mark.parametrize('mutation', ['stale', 'future', 'naive', 'invalid', 'capture_future', 'capture_naive'])
def test_report_and_receipt_clocks_cannot_escape_current_invocation(report_path, mutation):
    report = public_report()
    if mutation == 'stale': report['finished_at'] = (START-timedelta(microseconds=1)).isoformat()
    if mutation == 'future': report['finished_at'] = (NOW+timedelta(microseconds=1)).isoformat()
    if mutation == 'naive': report['finished_at'] = NOW.replace(tzinfo=None).isoformat()
    if mutation == 'invalid': report['finished_at'] = 'RAW_PRIVATE_REPORT'
    if mutation == 'capture_future': report['markets']['nfl']['captured_at'] = (NOW+timedelta(seconds=1)).isoformat()
    if mutation == 'capture_naive': report['markets']['nfl']['captured_at'] = NOW.replace(tzinfo=None).isoformat()
    report_path.write_text(json.dumps(report), encoding='utf-8')
    with pytest.raises(ValueError): validate(report_path)


@pytest.mark.parametrize('options', [dict(mode='daily'), dict(sport='cfb'), dict(sport='all'),
    dict(producer_status=1), dict(producer_status=3), dict(producer_status=True),
    dict(started_at=NOW.replace(tzinfo=None).isoformat()),
    dict(started_at=(NOW+timedelta(seconds=1)).isoformat())])
def test_invalid_or_failed_invocation_cannot_bless_an_existing_file(report_path, options):
    with pytest.raises(ValueError): validate(report_path, **options)


@pytest.mark.parametrize('mutation', ['mode', 'exit_status', 'execution', 'scope', 'extra_key',
    'missing_group', 'wrong_sport', 'extra_sport', 'wrong_group', 'props_requested'])
def test_invalid_status_and_public_scope_are_rejected(report_path, mutation):
    report = public_report()
    if mutation == 'mode': report['mode'] = 'public_daily'
    if mutation == 'exit_status': report['status'] = 'degraded'
    if mutation == 'execution': report['execution_ready'] = True
    if mutation == 'scope': report['scope'] = None
    if mutation == 'extra_key': report['private_extra'] = 'RAW_PRIVATE_REPORT'
    if mutation == 'missing_group': del report['histories']
    if mutation == 'wrong_sport': report['markets'] = {'cfb': dict(status='observed')}
    if mutation == 'extra_sport': report['schedules']['cfb'] = dict(status='complete')
    if mutation == 'wrong_group': report['schedules'] = []
    if mutation == 'props_requested': report['props']['nfl'] = dict(status='observed')
    report_path.write_text(json.dumps(report), encoding='utf-8')
    with pytest.raises(ValueError): validate(report_path)


def test_empty_receipt_report_is_not_ready(report_path):
    report = public_report('degraded')
    report['markets'] = report['schedules'] = {sport:dict(status='failed') for sport in ('nfl', 'nba')}
    report_path.write_text(json.dumps(report), encoding='utf-8')
    with pytest.raises(ValueError): validate(report_path, producer_status=2)


@pytest.mark.parametrize('raw', [b'', b'RAW_PRIVATE_REPORT', b'[]', b'{"mode":"public_monitor","mode":"public_monitor"}',
    b'{"value":NaN}', b'{"value":Infinity}', b'{"value":1e999}', b'\xff', b'x'*(1024*1024+1)],
    ids=['empty', 'non_json', 'array', 'duplicate', 'nan', 'infinity', 'overflow', 'invalid_utf8', 'oversize'])
def test_malformed_duplicate_nonfinite_and_unbounded_json_is_rejected(report_path, raw):
    report_path.write_bytes(raw)
    with pytest.raises((ValueError, UnicodeError)): validate(report_path)


def test_missing_file_is_not_ready(report_path):
    report_path.unlink()
    with pytest.raises(ValueError): validate(report_path)


@pytest.mark.parametrize('status,code', [('observed', 0), ('degraded', 2)])
def test_actual_daily_cli_writes_a_valid_receipt_before_its_original_exit(monkeypatch, tmp_path, capsys, status, code):
    from sportsbet import daily
    output = tmp_path/'current'/'report.json'
    report = public_report(status)
    run = AsyncMock(return_value=deepcopy(report))
    monkeypatch.setattr(daily, 'run', run)
    monkeypatch.setattr(sys, 'argv', ['daily', '--sport', 'both', '--mode', 'public_monitor',
                                    '--report-output', str(output)])
    if code:
        with pytest.raises(SystemExit) as error: daily.main()
        assert error.value.code == code
    else:
        daily.main()
    run.assert_awaited_once_with(['nfl', 'nba'], 'public_monitor', 20)
    assert json.loads(capsys.readouterr().out) == report
    assert validate(output, producer_status=code) == {
        'validated_public_report_receipts': 3 if code == 2 else 4}
    assert not output.with_name('report.json.tmp').exists()


@pytest.mark.parametrize('invalid', [False, True])
def test_validator_cli_outputs_only_aggregate_or_fixed_failure(monkeypatch, report_path, capsys, invalid):
    now = datetime.now(timezone.utc)
    if invalid: report_path.write_text('RAW_PRIVATE_REPORT', encoding='utf-8')
    else: report_path.write_text(json.dumps(public_report(now=now)), encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', [str(SCRIPT), '--report', str(report_path), '--mode', 'public_monitor',
        '--sport', 'both', '--producer-status', '0', '--started-at', (now-timedelta(minutes=2)).isoformat()])
    if invalid:
        with pytest.raises(SystemExit) as error: validator.main()
        assert str(error.value) == 'Public producer report validation failed.'
    else:
        validator.main()
    captured = capsys.readouterr()
    assert captured.err == '' and 'RAW_PRIVATE_REPORT' not in captured.out
    if not invalid: assert json.loads(captured.out) == {'validated_public_report_receipts': 4}


def test_public_producer_shell_syntax_is_valid():
    source = (ROOT/'.github/workflows/public-data.yml').read_text(encoding='utf-8')
    step = source.split('      - name: Update public market data\n', 1)[1].split('      - name:', 1)[0]
    script = textwrap.dedent(step.split('        run: |\n', 1)[1])
    windows_bash = Path(r'C:\Program Files\Git\bin\bash.exe')
    bash = str(windows_bash) if windows_bash.is_file() else shutil.which('bash')
    if bash is None: pytest.skip('Bash syntax checker is unavailable')
    result = subprocess.run([bash, '-n'], input=script, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
