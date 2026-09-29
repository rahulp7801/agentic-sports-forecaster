"""Append reviewed explicit receiving supplements without rewriting primary history."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from sportsbet.ingestion.cfb_final_evidence import digest, inspect_bundle
from sportsbet.ingestion.provenance import STAT_FIELDS, stat_row_sha256
from sportsbet.quant.audit_storage import ReadOnlyLedger, audit_database_url
from sportsbet.quant.cfb_history_completeness import build_report, load_primary, normalized

POLICY = 'cfb-explicit-receiving-v1'
PROVIDER = 'sportsdataverse_espn_supplement'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def plan_supplements(raw, rows, existing=(), *, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(raw, str) or not 0 < len(raw.encode('utf-8')) <= 25_000_000:
        raise ValueError('Invalid source bundle size')
    bundle = json.loads(raw); evidence = inspect_bundle(bundle, now=now)
    report = build_report(bundle, rows, cutoff=now.date().isoformat(), season_min=2004, now=now)
    if any(c['status'] not in ('verified_gap', 'complete') for c in report['comparisons']):
        raise ValueError('Every requested game requires matching primary and explicit final evidence')
    if any(w['status'] == 'primary_provenance_invalid' for w in report['windows']):
        raise ValueError('Primary history provenance invalid')
    indexed = {(r['athlete_id'], int(r['game_id'])): normalized(r) for r in rows}
    proofs = {(int(e['player_id']), int(e['game']['provider_event_id'])): e for e in evidence}
    prior = {(r['athlete_id'], r['game_id'], r['primary_record_sha256']): r for r in existing}
    if len(prior) != len(existing):
        raise ValueError('Duplicate existing supplement identity')
    updates = []; retained = 0
    for comparison in report['comparisons']:
        if comparison['status'] != 'verified_gap':
            continue
        key = (int(comparison['player_id']), int(comparison['game_id']))
        primary = indexed[key]; explicit = proofs[key]
        fields = comparison['explicit_missing_fields']
        effective = {k: primary[k] for k in STAT_FIELDS['cfb']} | fields
        # Keep the exact DB-shaped core row for the effective view's equality guard.
        original = {k: primary[k] for k in STAT_FIELDS['cfb']}
        original['game_id'] = str(original['game_id'])
        primary_observed = primary['source_observed_at']
        if isinstance(primary_observed, datetime):
            primary_observed = primary_observed.isoformat()
        manifest = dict(version=1, policy_version=POLICY, bundle_sha256=digest(raw),
            primary_record_sha256=primary['source_record_sha256'],
            primary_source_sha256=primary['source_sha256'],
            primary_player_sha256=primary['source_player_sha256'],
            primary_schedule_sha256=primary['source_schedule_sha256'],
            primary_observed_at=primary_observed, explicit_source=explicit['source_evidence'],
            explicit_source_sha256=explicit['source_sha256'], supplemented_fields=fields,
            effective_record_sha256=stat_row_sha256('cfb', effective))
        item = dict(athlete_id=key[0], game_id=str(key[1]),
            primary_record_sha256=primary['source_record_sha256'],
            bundle_sha256=digest(raw), primary_row=original,
            receiving_yards=effective['receiving_yards'], receptions=effective['receptions'],
            effective_record_sha256=manifest['effective_record_sha256'],
            source_sha256=digest(canonical(manifest)), manifest=manifest,
            observed_at=max(datetime.fromisoformat(primary_observed),
                datetime.fromisoformat(explicit['observed_at'])).isoformat())
        previous = prior.get((item['athlete_id'], item['game_id'], item['primary_record_sha256']))
        if previous is not None:
            if any(previous.get(k) != item[k] for k in ('source_sha256', 'effective_record_sha256', 'bundle_sha256')):
                raise ValueError('Existing supplement differs; append a reviewed new primary revision instead')
            retained += 1
            continue
        updates.append(item)
    updates.sort(key=lambda r: (r['athlete_id'], r['game_id'], r['primary_record_sha256']))
    return dict(bundle_sha256=digest(raw), updates=updates, retained=retained,
        plan_sha256=digest(canonical(updates)))


def existing_supplements(db, evidence):
    players = sorted({int(e['player_id']) for e in evidence})
    fields = ('athlete_id', 'game_id', 'primary_record_sha256', 'source_sha256',
        'effective_record_sha256', 'bundle_sha256')
    rows = db.execute('SELECT ' + ','.join(fields)
        + ' FROM public.cfb_receiving_supplements WHERE athlete_id=ANY(?)', (players,)).fetchall()
    return [dict(zip(fields, row, strict=True)) for row in rows]


def apply_bundle(conn, raw, *, expected_count, expected_plan_sha256, now=None):
    if type(expected_count) is not int or expected_count <= 0:
        raise ValueError('Positive reviewed count required')
    now = now or datetime.now(timezone.utc)
    evidence = inspect_bundle(json.loads(raw), now=now)
    players = sorted({int(e['player_id']) for e in evidence})
    # Lock the scoped primary history in a deterministic order before replanning.
    # Inserts for the same revision serialize on these existing parent rows.
    conn.execute('SELECT athlete_id,game_id FROM public.cfb_player_gamelogs '
        'WHERE athlete_id=ANY(%s) ORDER BY athlete_id,game_id FOR UPDATE', (players,)).fetchall()
    class Session:
        def execute(self, sql, args=()):
            return conn.execute(sql.replace('?', '%s'), args)
    db = Session()
    rows = load_primary(db, evidence, cutoff=now.date().isoformat(), season_min=2004)
    plan = plan_supplements(raw, rows, existing_supplements(db, evidence), now=now)
    if len(plan['updates']) != expected_count or plan['plan_sha256'] != expected_plan_sha256:
        raise ValueError('Primary history or supplement state changed; re-preview required')
    source = conn.execute('SELECT response_text FROM public.cfb_history_source_bundles '
        'WHERE bundle_sha256=%s', (plan['bundle_sha256'],)).fetchone()
    if source is not None and source[0] != raw:
        raise ValueError('Archived source commitment conflict')
    if source is None:
        conn.execute('INSERT INTO public.cfb_history_source_bundles(bundle_sha256,response_text) '
            'VALUES (%s,%s) ON CONFLICT DO NOTHING', (plan['bundle_sha256'], raw))
        retained = conn.execute('SELECT response_text FROM public.cfb_history_source_bundles '
            'WHERE bundle_sha256=%s', (plan['bundle_sha256'],)).fetchone()
        if retained is None or retained[0] != raw:
            raise ValueError('Archived source commitment conflict')
    from psycopg.types.json import Jsonb
    count = 0
    for item in plan['updates']:
        values = dict(item, primary_row=Jsonb(item['primary_row']), manifest=Jsonb(item['manifest']))
        columns = tuple(values)  # Internal schema only, never caller-supplied identifiers.
        cursor = conn.execute('INSERT INTO public.cfb_receiving_supplements ('
            + ','.join(columns) + ') VALUES (' + ','.join(['%s'] * len(columns)) + ')',
            tuple(values[c] for c in columns))
        count += cursor.rowcount
    if count != expected_count:
        raise ValueError('Unexpected supplement write count')
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--database-env')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-count', type=int)
    parser.add_argument('--expected-plan-sha256')
    args = parser.parse_args()
    if args.apply and (not args.expected_count or args.expected_count < 0 or not args.expected_plan_sha256):
        parser.error('--apply requires positive --expected-count and reviewed --expected-plan-sha256')
    from dotenv import load_dotenv
    load_dotenv()
    try:
        if args.bundle.stat().st_size > 25_000_000:
            raise ValueError('Oversized bundle')
        raw = args.bundle.read_text(encoding='utf-8'); evidence = inspect_bundle(json.loads(raw))
        url = audit_database_url(args.database_env)
        if args.apply:
            import psycopg
            with psycopg.connect(url.replace('postgresql+psycopg://', 'postgresql://', 1),
                    connect_timeout=15, options='-c statement_timeout=60000 -c lock_timeout=5000') as conn:
                count = apply_bundle(conn, raw, expected_count=args.expected_count,
                    expected_plan_sha256=args.expected_plan_sha256)
            print(json.dumps(dict(mode='applied', supplements=count, bundle_sha256=digest(raw))))
        else:
            ledger = ReadOnlyLedger(database_url=url)
            with ledger.snapshot(), ledger.connect() as db:
                rows = load_primary(db, evidence, cutoff=datetime.now(timezone.utc).date().isoformat(), season_min=2004)
                plan = plan_supplements(raw, rows, existing_supplements(db, evidence))
            print(json.dumps(dict(mode='read_only_preview', proposed=len(plan['updates']),
                retained=plan['retained'], bundle_sha256=plan['bundle_sha256'], plan_sha256=plan['plan_sha256']), indent=2))
    except Exception as exc:
        raise SystemExit(f'CFB history supplement unavailable: {type(exc).__name__}') from None


if __name__ == '__main__':
    main()
