"""Preview or atomically apply archived explicit CFB passing/rushing finals."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from sportsbet.ingestion.cfb_nonreceiving_evidence import inspect_bundle, plan_recovery
from sportsbet.ledger import json_object
from sportsbet.quant.audit_storage import ReadOnlyLedger, audit_database_url
from sportsbet.quant.nfl_final_recovery import apply_plan


def pending_rows(db, evidence):
    players = sorted({item['player_id'] for item in evidence})
    dates = sorted({item['game']['date'] for item in evidence})
    if not players or not dates:
        return []
    rows = db.execute("""SELECT id,payload FROM predictions WHERE outcome IS NULL
        AND payload::jsonb->>'sport'='cfb' AND payload::jsonb->>'player_id'=ANY(?)
        AND payload::jsonb->>'game_date'=ANY(?)
        AND payload::jsonb->>'prop_type'=ANY(?)""",
        (players, dates, ['pass_yds', 'rush_yds'])).fetchall()
    return [json_object(payload) | dict(prediction_id=key, outcome=None) for key, payload in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--database-env')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-count', type=int)
    args = parser.parse_args()
    if args.apply and (args.expected_count is None or args.expected_count <= 0):
        parser.error('--apply requires a positive reviewed --expected-count')
    from dotenv import load_dotenv
    load_dotenv()
    try:
        if args.bundle.stat().st_size > 25_000_000:
            raise ValueError('Oversized recovery bundle')
        raw = args.bundle.read_bytes(); evidence = inspect_bundle(json.loads(raw))
        url = audit_database_url(args.database_env)
        ledger = ReadOnlyLedger(database_url=url)
        with ledger.snapshot(), ledger.connect() as db:
            plan = plan_recovery(pending_rows(db, evidence), evidence)
        count = len(plan['updates'])
        if args.expected_count is not None and count != args.expected_count:
            raise ValueError('Recovery count differs from reviewed preview')
        applied = 0
        if args.apply:
            import psycopg
            with psycopg.connect(url.replace('postgresql+psycopg://', 'postgresql://', 1),
                    connect_timeout=15, options='-c statement_timeout=60000 '
                    '-c lock_timeout=5000 -c idle_in_transaction_session_timeout=60000') as conn:
                conn.execute('SET LOCAL search_path TO analytics, public')
                conn.execute("SET LOCAL application_name='sportsbet_explicit_cfb_nonreceiving_recovery'")
                applied = apply_plan(conn, plan, sport='cfb')
        print(json.dumps(dict(mode='applied' if args.apply else 'read_only_preview',
            bundle_sha256=hashlib.sha256(raw).hexdigest(),
            players=dict(Counter(item['status'] for item in evidence)),
            proposed_results=count, applied_results=applied,
            unresolved=len(plan['unresolved']),
            outcomes=dict(Counter(str(item['outcome']) for item in plan['updates'])),
            accepted_forecasts=sum(item['payload'].get('accepted') is True
                for item in plan['updates'])), indent=2))
    except Exception as exc:
        raise SystemExit(f'Explicit CFB passing/rushing recovery unavailable: {type(exc).__name__}') from None


if __name__ == '__main__':
    main()
