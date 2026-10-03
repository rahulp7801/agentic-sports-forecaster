"""Verify exact worker publication without exposing private APIs or owner cookies."""
import importlib.util
import json
import os
from pathlib import Path
from datetime import datetime

import psycopg


def receipt_entries(report):
    entries = []
    for sport in ('nfl', 'nba', 'cfb'):
        for category, prefix in (('markets', 'markets'), ('schedules', 'schedule')):
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


def main():
    receipt = Path(os.environ['PUBLIC_DATA_REPORT_PATH'])
    if receipt.stat().st_size > 1024 * 1024:
        raise ValueError('Capture report is too large')
    report = json.loads(receipt.read_text(encoding='utf-8'))
    spec = importlib.util.spec_from_file_location('transaction_preflight',
        Path(__file__).with_name('production-transaction-preflight.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dsn = module.hosted_read_dsn(os.environ['DATABASE_URL'])
    with psycopg.connect(dsn, connect_timeout=5, options='-c statement_timeout=5000 -c default_transaction_read_only=on') as conn:
        def read(key):
            row = conn.execute('SELECT payload FROM public.dashboard_snapshots WHERE snapshot_key=%s', (key,)).fetchone()
            return row[0] if row else None
        count = verify_captures(report, read)
    print(json.dumps({'verified_snapshot_receipts': count}))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Never echo connection data, emails or provider bodies to Actions logs.
        raise SystemExit('Published snapshot receipt verification failed.') from None
