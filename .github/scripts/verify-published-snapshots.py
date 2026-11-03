"""Verify exact worker publication without exposing private APIs or owner cookies."""
import importlib.util
import json
import os
import sys
from pathlib import Path
from datetime import datetime

import psycopg
from sportsbet.diagnostics import emit_failure, failure_record

CAPTURE_QUERY = "SELECT payload -> 'captured_at' FROM public.dashboard_snapshots WHERE snapshot_key=%s"


def receipt_entries(report):
    entries = []
    for sport in ('nfl', 'nba', 'cfb'):
        for category, prefix in (('markets', 'markets'), ('schedules', 'schedule'), ('slates', 'slate')):
            captured = report.get(category, {}).get(sport, {}).get('captured_at')
            if captured is None:
                continue
            if not isinstance(captured, str):
                raise ValueError('Invalid capture receipt')
            timestamp = datetime.fromisoformat(captured.replace('Z', '+00:00'))
            if timestamp.tzinfo is None:
                raise ValueError('Capture receipt lacks timezone')
            entries.append((prefix + ':' + sport, captured))
    if not entries:
        raise ValueError('No capture receipts to verify')
    return entries


def verify_captures(report, read):
    entries = receipt_entries(report)
    for key, captured in entries:
        row = read(key)
        if not isinstance(row, dict) or row.get('captured_at') != captured:
            raise ValueError(key + ': published capture does not match this run')
    return len(entries)


def read_capture(connection, key):
    """Read only the original JSON capture value, retaining its JSON type."""
    row = connection.execute(CAPTURE_QUERY, (key,)).fetchone()
    return {'captured_at': row[0]} if row else None


def emit_read_retry(error: Exception) -> None:
    try:
        record = failure_record(error, operation='published_snapshot_receipt', stage='snapshot_read')
        record['diagnostic_kind'] = 'operation_retry'
        print(json.dumps(record, separators=(',', ':'), allow_nan=False), file=sys.stderr)
    except Exception:
        # A diagnostic failure must not replace the interrupted read.
        pass


def main():
    stage = 'receipt'
    try:
        receipt = Path(os.environ['PUBLIC_DATA_REPORT_PATH'])
        if receipt.stat().st_size > 1024 * 1024:
            raise ValueError('Capture report is too large')
        report = json.loads(receipt.read_text(encoding='utf-8'))
        stage = 'dsn'
        spec = importlib.util.spec_from_file_location('transaction_preflight',
            Path(__file__).with_name('production-transaction-preflight.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        dsn = module.hosted_read_dsn(os.environ['DATABASE_URL'])
        for attempt in range(2):
            interrupted_read = None
            try:
                stage = 'connect'
                with psycopg.connect(dsn, connect_timeout=5,
                                     options='-c statement_timeout=5000 -c default_transaction_read_only=on') as conn:
                    def read(key):
                        nonlocal stage, interrupted_read
                        stage = 'snapshot_read'
                        try:
                            value = read_capture(conn, key)
                        except psycopg.errors.ConnectionFailure as error:
                            interrupted_read = error
                            raise
                        stage = 'verify'
                        return value
                    stage = 'verify'
                    count = verify_captures(report, read)
                    stage = 'close'
            except Exception as error:
                if interrupted_read is not None and error is not interrupted_read:
                    stage = 'close'
                # Only the original read error may trigger a replay after the connection closes.
                if attempt or error is not interrupted_read:
                    raise
                emit_read_retry(error)
            else:
                break
        stage = 'output'
        print(json.dumps({'verified_snapshot_receipts': count}))
    except Exception as error:
        emit_failure(error, operation='published_snapshot_receipt', stage=stage)
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Never echo connection data, emails or provider bodies to Actions logs.
        raise SystemExit('Published snapshot receipt verification failed.') from None
