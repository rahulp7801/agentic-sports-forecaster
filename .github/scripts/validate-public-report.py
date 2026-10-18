"""Validate a just-completed public producer report without database or HTTP I/O."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import math
from pathlib import Path
import re


MAX_REPORT_BYTES = 1024 * 1024
GROUPS = ('histories', 'markets', 'schedules', 'settlements', 'props', 'profiles')
PROFILE_COUNTS = {'profiles': 1000, 'unavailable': 1000, 'signal_identities': 1000,
                  'public_identities': 5000, 'selected_events': 20, 'selected_players': 1000}
PROFILE_INPUT_REJECTIONS = {
    'snapshots': frozenset(('invalid_set', 'decode')),
    'capture_pins': frozenset(('shape', 'mismatch')),
    'handoff': frozenset(('shape', 'status', 'chronology', 'integrity')),
    'slate': frozenset(('shape', 'chronology', 'sources')),
    'target': frozenset(('identity', 'receipt', 'chronology')),
    'event': frozenset(('identity', 'join')),
    'quote': frozenset(('identity', 'receipt', 'chronology')),
}


def _clock(value):
    if not isinstance(value, str):
        raise ValueError('Invalid report clock')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('Invalid report clock')
    return result


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate report field')
        result[key] = value
    return result


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Nonfinite report number')
    return result


def _reject_constant(value):
    raise ValueError('Nonfinite report number')


def _receipt_entries(report):
    # Reuse the exact receipt contract without invoking the verifier's DB main.
    spec = importlib.util.spec_from_file_location('public_report_receipts',
        Path(__file__).with_name('verify-published-snapshots.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.receipt_entries(report)


def _profile_result(value, mode):
    """Validate bounded aggregate diagnostics, never private identity rows."""
    if mode == 'public_monitor':
        if value != {'status': 'not_requested', 'reason': 'public_daily_only'}:
            raise ValueError('Monitor requested profile collection')
        return
    status = value.get('status')
    if status == 'failed':
        if (not {'status', 'error_type'} <= set(value) <= {'status', 'error_type', 'sqlstate'}
                or not isinstance(value['error_type'], str)
                or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,99}', value['error_type'])
                or ('sqlstate' in value and (not isinstance(value['sqlstate'], str)
                    or not re.fullmatch('[0-9A-Z]{5}', value['sqlstate'])))):
            raise ValueError('Invalid profile failure diagnostic')
        return
    rejected = value.get('public_input_status') == 'rejected'
    fields = {'status', 'public_input_status', *PROFILE_COUNTS}
    if rejected:
        fields |= {'rejection_stage', 'rejection_reason'}
    if (set(value) != fields
            or any(type(value[key]) is not int or not 0 <= value[key] <= limit
                   for key, limit in PROFILE_COUNTS.items())
            or value['public_input_status'] not in ('observed', 'missing', 'rejected')
            or value['profiles'] + value['unavailable'] > value['selected_players']
            or value['selected_players'] > value['selected_events'] * 50):
        raise ValueError('Invalid profile result counters')
    if rejected and (type(value['rejection_stage']) is not str
            or type(value['rejection_reason']) is not str
            or value['rejection_reason'] not in PROFILE_INPUT_REJECTIONS.get(value['rejection_stage'], ())):
        raise ValueError('Invalid profile input rejection diagnostic')
    expected = 'complete' if value['public_input_status'] == 'observed' and value['unavailable'] == 0 else 'degraded'
    if status != expected:
        raise ValueError('Profile status contradicts its input or availability')


def validate_report(path, *, mode, sport, producer_status, started_at, now=None):
    if (mode not in ('public_daily', 'public_monitor') or sport not in ('both', 'nfl', 'nba')
            or type(producer_status) is not int or producer_status not in (0, 2)):
        raise ValueError('Unsupported public producer invocation')
    started = _clock(started_at)
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.utcoffset() is None or started > now:
        raise ValueError('Invalid invocation clock')
    path = Path(path)
    if (path.is_symlink() or path.is_junction() or not path.is_file()
            or not 0 < path.stat().st_size <= MAX_REPORT_BYTES):
        raise ValueError('Public producer report unavailable or unbounded')
    with path.open('rb') as stream:
        raw = stream.read(MAX_REPORT_BYTES + 1)
    if not 0 < len(raw) <= MAX_REPORT_BYTES:
        raise ValueError('Public producer report unavailable or unbounded')
    report = json.loads(raw, object_pairs_hook=_object,
                        parse_float=_finite_float, parse_constant=_reject_constant)
    expected = {'mode', 'finished_at', 'status', 'execution_ready', 'scope', *GROUPS}
    if (not isinstance(report, dict) or set(report) != expected or report['mode'] != mode
            or report['execution_ready'] is not False
            or report['status'] != ('observed' if producer_status == 0 else 'degraded')
            or not isinstance(report['scope'], str) or not 1 <= len(report['scope']) <= 2048):
        raise ValueError('Public producer report scope or status changed')
    finished = _clock(report['finished_at'])
    if not started <= finished <= now:
        raise ValueError('Public producer report is outside this invocation')
    sports = {'nfl', 'nba'} if sport == 'both' else {sport}
    for group in GROUPS:
        values = report[group]
        if (not isinstance(values, dict) or set(values) != sports
                or any(not isinstance(value, dict) for value in values.values())):
            raise ValueError('Public producer report sport scope changed')
    allowed = dict(markets={'observed', 'degraded', 'failed'},
                   schedules={'complete', 'partial', 'unavailable'}, props={'not_requested'},
                   histories={'complete', 'failed'} if mode == 'public_daily' else {'not_requested'},
                   settlements={'complete', 'degraded', 'blocked', 'failed'}
                   if mode == 'public_daily' else {'not_requested'},
                   profiles={'complete', 'degraded', 'failed'} if mode == 'public_daily' else {'not_requested'})
    for group in GROUPS:
        for value in report[group].values():
            status = value.get('status')
            if not isinstance(status, str) or status not in allowed[group]:
                raise ValueError('Public producer component status changed')
            if group == 'schedules' or (group == 'markets' and status != 'failed'):
                if 'captured_at' not in value or _clock(value['captured_at']) > finished:
                    raise ValueError('Published component capture is missing or invalid')
            elif group == 'markets' and 'captured_at' in value:
                raise ValueError('Failed market cannot claim a completed capture')
            if group == 'profiles':
                _profile_result(value, mode)
            if group == 'schedules':
                if 'slate_captured_at' not in value or _clock(value['slate_captured_at']) > finished:
                    raise ValueError('Published slate capture is missing or invalid')
    if any(value.get('status') != 'not_requested'
           or value.get('reason') != 'public_only_collection' for value in report['props'].values()):
        raise ValueError('Public producer requested unsupported prop collection')
    health_groups = ('markets', 'schedules') + (('histories', 'settlements', 'profiles')
                                               if mode == 'public_daily' else ())
    healthy = all(value['status'] in ('complete', 'observed')
                  for group in health_groups for value in report[group].values())
    if report['status'] != ('observed' if healthy else 'degraded'):
        raise ValueError('Public producer status contradicts component coverage')
    entries = _receipt_entries(report)
    if any(_clock(captured) > finished for _, captured in entries):
        raise ValueError('Published capture postdates producer completion')
    return {'validated_public_report_receipts': len(entries)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    parser.add_argument('--mode', required=True)
    parser.add_argument('--sport', required=True)
    parser.add_argument('--producer-status', required=True)
    parser.add_argument('--started-at', required=True)
    args = parser.parse_args()
    try:
        summary = validate_report(args.report, mode=args.mode, sport=args.sport,
            producer_status=int(args.producer_status), started_at=args.started_at)
    except Exception:
        raise SystemExit('Public producer report validation failed.') from None
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
