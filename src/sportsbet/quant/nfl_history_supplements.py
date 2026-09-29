"""Archive reviewed NFL receiving history; activation is a separate model change.

Only explicit final stats corroborated by participation qualify. No fetching,
primary-history changes, model reads, forecasts, or settlements occur here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from sportsbet.ingestion.nfl_final_evidence import digest, inspect_bundle
from sportsbet.ingestion.provenance import stat_row_sha256
from sportsbet.ledger import utc_timestamp
from sportsbet.quant.audit_storage import ReadOnlyLedger, audit_database_url

POLICY = 'nfl-explicit-receiving-v1'
MAX_BYTES = 25_000_000


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def inspect_raw(raw, now):
    if not isinstance(raw, str) or not 0 < len(raw.encode('utf-8')) <= MAX_BYTES:
        raise ValueError('Invalid source bundle size')
    evidence = inspect_bundle(json.loads(raw), now=now)
    if not evidence or any(e['status'] != 'verified_explicit_stats' for e in evidence):
        raise ValueError('Every requested game requires explicit final receiving statistics')
    return evidence


def plan_supplements(raw, rows, games, existing=(), *, now=None):
    now = now or datetime.now(timezone.utc)
    evidence = inspect_raw(raw, now)
    primary = {(r['player_id'], r['season'], r['week']): r for r in rows}
    schedules = {g['game_id']: g for g in games}
    prior = {(r['player_id'], r['season'], r['week']): r for r in existing}
    if len(primary) != len(rows) or len(schedules) != len(games) or len(prior) != len(existing):
        raise ValueError('Duplicate history identity')
    keys = [(e['player_id'], e['stat_row']['season'], e['stat_row']['week']) for e in evidence]
    if len(set(keys)) != len(keys):
        raise ValueError('Duplicate explicit player-week identity')
    identity_at = utc_timestamp(json.loads(raw)['identity']['retrieved_at'])
    updates = []; retained = complete = 0
    for e in evidence:
        row = e['stat_row']; key = (row['player_id'], row['season'], row['week'])
        participation = e['source_evidence']['participation']
        game_id = participation['row']['game_id']; game = schedules.get(game_id)
        if game is None or any(str(game[k]) != str(v) for k, v in dict(
                season=row['season'], week=row['week'], game_date=e['game']['date'],
                home_team=participation['home_team'], away_team=participation['away_team']).items()):
            raise ValueError('Exact stored game identity required')
        manifest = dict(version=1, policy_version=POLICY, bundle_sha256=digest(raw),
            game=e['game'], explicit_source=e['source_evidence'],
            explicit_source_sha256=e['source_sha256'], stat_record_sha256=e['stat_record_sha256'])
        # Identity availability is part of the history receipt, even when later
        # than the final-stat and participation receipts.
        item = dict(player_id=key[0], season=key[1], week=key[2], game_id=game_id,
            bundle_sha256=digest(raw), stat_row=row,
            stat_record_sha256=e['stat_record_sha256'], source_sha256=digest(canonical(manifest)),
            manifest=manifest, observed_at=max(identity_at, utc_timestamp(e['observed_at'])).isoformat())
        previous = prior.get(key)
        if previous is not None and any(previous.get(k) != item[k] for k in
                ('bundle_sha256', 'stat_record_sha256', 'source_sha256', 'game_id')):
            raise ValueError('Existing supplement differs; explicit revision review required')
        current = primary.get(key)
        if current is not None:
            if (current.get('source_provider') != 'nflverse'
                    or not re.fullmatch('[0-9a-f]{64}', current.get('source_sha256', ''))
                    or stat_row_sha256('nfl', current) != current.get('source_record_sha256')
                    or not utc_timestamp(e['game']['game_time']) <= utc_timestamp(current['source_observed_at']) <= now
                    or any(current.get(k) != row[k] for k in ('team', 'receiving_yards', 'receptions'))):
                raise ValueError('Existing primary receiving history conflicts or has invalid provenance')
            complete += 1
        elif previous is None:
            updates.append(item)
        if previous is not None:
            retained += 1
    updates.sort(key=lambda r: (r['player_id'], r['season'], r['week']))
    return dict(bundle_sha256=digest(raw), updates=updates, retained=retained,
        complete=complete, plan_sha256=digest(canonical(updates)))


def load_state(db, evidence):
    ids = sorted({e['player_id'] for e in evidence})
    game_ids = sorted({e['source_evidence']['participation']['row']['game_id'] for e in evidence})
    rows = db.execute('SELECT to_jsonb(p) FROM public.player_stats p WHERE player_id=ANY(?)', (ids,)).fetchall()
    games = db.execute('SELECT to_jsonb(g) FROM public.games g WHERE game_id=ANY(?)', (game_ids,)).fetchall()
    existing = db.execute('SELECT to_jsonb(s) FROM public.nfl_receiving_supplements s WHERE player_id=ANY(?)', (ids,)).fetchall()
    def values(result):
        return [json.loads(r[0]) if isinstance(r[0], str) else r[0] for r in result]
    return values(rows), values(games), values(existing)


def apply_bundle(conn, raw, *, expected_count, expected_plan_sha256, now=None):
    if type(expected_count) is not int or expected_count <= 0:
        raise ValueError('Positive reviewed count required')
    now = now or datetime.now(timezone.utc)
    evidence = inspect_raw(raw, now)
    # Missing primary rows cannot be row-locked. A bounded table SHARE lock
    # prevents ingestion inserting them between the re-preview and commit.
    conn.execute('LOCK TABLE public.player_stats, public.games IN SHARE MODE')
    class Session:
        def execute(self, sql, args=()):
            return conn.execute(sql.replace('?', '%s'), args)
    plan = plan_supplements(raw, *load_state(Session(), evidence), now=now)
    if len(plan['updates']) != expected_count or plan['plan_sha256'] != expected_plan_sha256:
        raise ValueError('History or supplement state changed; re-preview required')
    conn.execute('INSERT INTO public.nfl_history_source_bundles(bundle_sha256,response_text) '
        'VALUES (%s,%s) ON CONFLICT DO NOTHING', (plan['bundle_sha256'], raw))
    source = conn.execute('SELECT response_text FROM public.nfl_history_source_bundles '
        'WHERE bundle_sha256=%s', (plan['bundle_sha256'],)).fetchone()
    if source is None or source[0] != raw:
        raise ValueError('Archived source commitment conflict')
    from psycopg.types.json import Jsonb
    count = 0
    for item in plan['updates']:
        values = dict(item, stat_row=Jsonb(item['stat_row']), manifest=Jsonb(item['manifest']))
        cursor = conn.execute('''INSERT INTO public.nfl_receiving_supplements
            (player_id,season,week,game_id,bundle_sha256,stat_row,stat_record_sha256,source_sha256,manifest,observed_at)
            VALUES (%(player_id)s,%(season)s,%(week)s,%(game_id)s,%(bundle_sha256)s,
                %(stat_row)s,%(stat_record_sha256)s,%(source_sha256)s,%(manifest)s,%(observed_at)s)''', values)
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
        if args.bundle.stat().st_size > MAX_BYTES:
            raise ValueError('Oversized bundle')
        raw = args.bundle.read_text(encoding='utf-8'); now = datetime.now(timezone.utc)
        evidence = inspect_raw(raw, now); url = audit_database_url(args.database_env)
        if args.apply:
            import psycopg
            with psycopg.connect(url.replace('postgresql+psycopg://', 'postgresql://', 1),
                    connect_timeout=15, options='-c statement_timeout=60000 -c lock_timeout=5000') as conn:
                count = apply_bundle(conn, raw, expected_count=args.expected_count,
                    expected_plan_sha256=args.expected_plan_sha256, now=now)
            result = dict(mode='applied', supplements=count, bundle_sha256=digest(raw))
        else:
            ledger = ReadOnlyLedger(database_url=url)
            with ledger.snapshot(), ledger.connect() as db:
                plan = plan_supplements(raw, *load_state(db, evidence), now=now)
            result = dict(mode='read_only_preview', proposed=len(plan['updates']),
                retained=plan['retained'], complete=plan['complete'],
                bundle_sha256=plan['bundle_sha256'], plan_sha256=plan['plan_sha256'])
        print(json.dumps(result, indent=2))
    except Exception as exc:
        raise SystemExit(f'NFL history supplement unavailable: {type(exc).__name__}') from None


if __name__ == '__main__':
    main()
