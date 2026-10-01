"""Retain the frozen NFL receiving audit in the restricted database only."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from sportsbet.quant.audit_storage import audit_database_url
from sportsbet.quant import model_selection_paper as paper
from sportsbet.quant import nfl_receiving_accuracy_v1 as frozen

PROTOCOL = frozen.PROTOCOL['version']
MAX_BYTES = 2_000_000
RECEIPT_FIELDS = ('protocol', 'sport', 'game_id', 'player_id', 'prediction_id',
                  'decision_at', 'valid_until', 'recorded_at', 'payload', 'payload_sha256')


def referenced_ids(receipts: list[dict]) -> list[str]:
    """Load enough predictions to let the frozen verifier identify bad receipts."""
    ids = {r['prediction_id'] for r in receipts}
    for receipt in receipts:
        try:
            evidence = json.loads(receipt['payload'])['evidence']
            for row in evidence:
                if isinstance(row, dict) and isinstance(row.get('prediction_id'), str):
                    ids.add(row['prediction_id'])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass
    return sorted(ids)


def read_evidence(database_url: str) -> tuple[list[dict], list[dict]]:
    ledger = paper.storage.PaperLedger(database_url=database_url)
    with ledger.snapshot():
        with ledger.connect() as db:
            if db.execute('SELECT current_user').fetchone()[0] != 'sportsbet_worker':
                raise PermissionError('Prospective audit requires the restricted worker role')
            raw = db.execute("""SELECT protocol,sport,game_id,player_id,prediction_id,
                decision_at,valid_until,recorded_at,payload,payload_sha256
                FROM paper_selections WHERE protocol=? AND sport=?""",
                (paper.PROTOCOL['policies']['raw_model'], 'nfl')).fetchall()
        receipts = [dict(zip(RECEIPT_FIELDS, row, strict=True)) for row in raw]
        ledger.ids = referenced_ids(receipts)
        predictions = ledger.predictions()
    return receipts, predictions


def encode_report(report: dict) -> tuple[datetime, str, str]:
    if (report.get('protocol') != frozen.PROTOCOL or report.get('promote') is not False
            or report.get('target_verified') is not False):
        raise ValueError('Frozen audit report contract changed')
    observed_at = datetime.fromisoformat(report['observed_at'].replace('Z', '+00:00'))
    if observed_at.utcoffset() is None:
        raise ValueError('Audit timestamp requires a timezone')
    payload = json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if not 0 < len(payload.encode()) <= MAX_BYTES:
        raise ValueError('Private audit report exceeds storage limit')
    return observed_at, payload, hashlib.sha256(payload.encode()).hexdigest()


def store_report(database_url: str, report: dict) -> None:
    import psycopg
    observed_at, payload, digest = encode_report(report)
    with psycopg.connect(database_url.replace('postgresql+psycopg://', 'postgresql://', 1),
                         connect_timeout=15) as conn:
        if conn.execute('SELECT current_user').fetchone()[0] != 'sportsbet_worker':
            raise PermissionError('Prospective audit requires the restricted worker role')
        conn.execute("""INSERT INTO analytics.prospective_audit_reports
            (protocol,observed_at,payload,payload_sha256) VALUES (%s,%s,%s,%s)""",
            (PROTOCOL, observed_at, payload, digest))


def run() -> None:
    database_url = audit_database_url()
    receipts, predictions = read_evidence(database_url)
    report = frozen.audit(receipts, predictions, datetime.now(timezone.utc))
    store_report(database_url, report)


def main() -> None:
    try:
        run()
        print('Private prospective receiving audit stored')
    except Exception as exc:
        # Never print report content, selected player IDs, credentials or SQL details.
        print(f'Private prospective receiving audit unavailable: {type(exc).__name__}')
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
