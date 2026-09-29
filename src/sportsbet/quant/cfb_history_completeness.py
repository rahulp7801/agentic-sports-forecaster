"""Read-only CFB receiving-history completeness audit against archived finals.

This is a current-snapshot data-quality comparison, never an as-of backtest or
an instruction to replace missing categories with zero. It cannot write history.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from sportsbet.ingestion.cfb_final_evidence import digest, inspect_bundle
from sportsbet.ingestion.provenance import STAT_FIELDS, stat_row_sha256
from sportsbet.ledger import utc_timestamp
from sportsbet.quant.audit_storage import ReadOnlyLedger, audit_database_url

RECEIVING_FIELDS = ('receiving_yards', 'receptions')
PROVENANCE_FIELDS = ('source_provider', 'source_sha256', 'source_player_sha256',
    'source_schedule_sha256', 'source_record_sha256', 'source_observed_at')
IDENTITY_FIELDS = ('game_id', 'athlete_id', 'season', 'week', 'game_date',
    'team_id', 'opponent_id', 'is_home')
MAX_ROWS = 10_000


def normalized(row):
    result = dict(row)
    if not re.fullmatch('[1-9][0-9]{0,14}', str(result['game_id'])):
        raise ValueError('Invalid primary event identity')
    result['game_id'] = int(result['game_id'])
    value = result['game_date']
    result['game_date'] = value.isoformat() if type(value) is date else value
    date.fromisoformat(result['game_date'])
    return result


def valid_primary(row, now):
    try:
        if row['source_provider'] != 'sportsdataverse_espn':
            return False
        for key in PROVENANCE_FIELDS[1:-1]:
            if not isinstance(row[key], str) or not re.fullmatch('[0-9a-f]{64}', row[key]):
                return False
        source_hash = digest(json.dumps(dict(player=row['source_player_sha256'],
            schedule=row['source_schedule_sha256']), sort_keys=True, separators=(',', ':')))
        raw_observed = row['source_observed_at']
        observed = utc_timestamp(raw_observed.isoformat() if isinstance(raw_observed, datetime) else raw_observed)
        return (source_hash == row['source_sha256']
            and stat_row_sha256('cfb', row) == row['source_record_sha256']
            and date.fromisoformat(row['game_date']) <= observed.date()
            and observed <= now)
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return False


def recent_sample(rows, field, limit):
    # Match production: filter non-NULL first, then take the most recent N.
    selected = sorted((r for r in rows if r[field] is not None),
        key=lambda r: (r['game_date'], str(r['game_id'])), reverse=True)[:limit]
    return dict(n=len(selected), mean=(sum(r[field] for r in selected) / len(selected)
        if selected else None), game_ids=[str(r['game_id']) for r in selected])


def build_report(bundle, primary_rows, *, cutoff, season_min, limit=40, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = date.fromisoformat(cutoff)
    if (type(season_min) is not int or not 2004 <= season_min <= cutoff.year
            or type(limit) is not int or not 1 <= limit <= 40
            or cutoff > now.date() or len(primary_rows) > MAX_ROWS):
        raise ValueError('Invalid audit scope')
    evidence = inspect_bundle(bundle, now=now)
    players = {int(e['player_id']) for e in evidence}
    by_key = {}
    for raw in primary_rows:
        row = normalized(raw)
        key = (row['athlete_id'], row['game_id'])
        if key in by_key:
            raise ValueError('Duplicate primary player/game')
        if (row['athlete_id'] not in players or row['season'] < season_min
                or date.fromisoformat(row['game_date']) >= cutoff):
            raise ValueError('Primary rows outside requested scope')
        by_key[key] = row
    checked = {key: valid_primary(row, now) for key, row in by_key.items()}
    supplements = {}; comparisons = []
    for item in evidence:
        event = item['game']['provider_event_id']
        record = dict(player_id=item['player_id'], game_id=event)
        if item['status'] != 'verified_explicit_stats':
            comparisons.append(record | dict(status='source_unavailable', reason=item['reason']))
            continue
        explicit = item['stat_row']
        record.update(source_sha256=item['source_sha256'], sources=item['source_evidence']['sources'])
        if explicit['season'] < season_min or date.fromisoformat(explicit['game_date']) >= cutoff:
            comparisons.append(record | dict(status='outside_scope'))
            continue
        key = (explicit['athlete_id'], explicit['game_id'])
        row = by_key.get(key)
        if row is None:
            comparisons.append(record | dict(status='primary_game_missing'))
            continue
        record['primary_record_sha256'] = row['source_record_sha256']
        if not checked[key]:
            comparisons.append(record | dict(status='primary_provenance_invalid'))
            continue
        conflicts = [f for f in IDENTITY_FIELDS if row[f] != explicit[f]]
        for activity in item['source_evidence']['offensive_activity']:
            field = activity['category'] + '_yards'
            if row[field] is not None and row[field] != activity['yards']:
                conflicts.append(field)
        conflicts += [f for f in RECEIVING_FIELDS
            if row[f] is not None and row[f] != explicit[f]]
        if conflicts:
            comparisons.append(record | dict(status='source_conflict', fields=sorted(set(conflicts))))
            continue
        missing = {f: explicit[f] for f in RECEIVING_FIELDS if row[f] is None}
        if missing:
            supplements[key] = missing
        comparisons.append(record | dict(status='verified_gap' if missing else 'complete',
            explicit_missing_fields=missing, player_label_differs=row['player_name'] != explicit['player_name']))
    windows = []
    for player in sorted(players):
        rows = [r for k, r in by_key.items() if k[0] == player]
        invalid = sum(not checked[k] for k in by_key if k[0] == player)
        if invalid:
            windows.append(dict(player_id=str(player), status='primary_provenance_invalid', invalid_rows=invalid))
            continue
        supplemented = [r | supplements.get((r['athlete_id'], r['game_id']), {}) for r in rows]
        for field in RECEIVING_FIELDS:
            before = recent_sample(rows, field, limit)
            after = recent_sample(supplemented, field, limit)
            windows.append(dict(player_id=str(player), field=field, status='descriptive_only',
                scoped_primary_games=len(rows),
                remaining_unverified_null_game_ids=[str(r['game_id']) for r in supplemented if r[field] is None],
                primary=before, hypothetical_with_verified_gaps=after,
                added_game_ids=[g for g in after['game_ids'] if g not in before['game_ids']],
                displaced_game_ids=[g for g in before['game_ids'] if g not in after['game_ids']]))
    return dict(version=1, mode='read_only', observed_at=now.isoformat(),
        scope=dict(exclusive_game_date=cutoff.isoformat(), season_min=season_min, last_n_games=limit,
            players=len(players), primary_rows=len(by_key), archived_player_games=len(evidence)),
        limitations=['Targeted archived games only; not a complete participation census.',
            'Current source snapshot; receipts may postdate the cutoff, so this is not an as-of backtest.',
            'Hypothetical sample changes do not establish predictive improvement or edge.',
            'Missing games, unconfirmed participation and source conflicts are not supplemented.'],
        counts=dict(Counter(r['status'] for r in comparisons)), comparisons=comparisons, windows=windows)


def load_primary(db, evidence, *, cutoff, season_min):
    players = sorted({int(e['player_id']) for e in evidence})
    columns = STAT_FIELDS['cfb'] + PROVENANCE_FIELDS
    # Only static schema constants enter SQL; all scope values are bound.
    sql = ('SELECT ' + ','.join(columns) + ' FROM public.cfb_player_gamelogs'
        ' WHERE athlete_id=ANY(?) AND season>=? AND game_date<?'
        ' ORDER BY athlete_id,game_date DESC,game_id DESC LIMIT ?')
    rows = db.execute(sql, (players, season_min, date.fromisoformat(cutoff), MAX_ROWS + 1)).fetchall()
    if len(rows) > MAX_ROWS:
        raise ValueError('Primary history exceeds audit bound')
    return [dict(zip(columns, row, strict=True)) for row in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--cutoff', required=True, help='Exclusive UTC game date; current snapshot only')
    parser.add_argument('--season-min', type=int, required=True)
    parser.add_argument('--last-n-games', type=int, default=40)
    parser.add_argument('--database-env')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv()
    try:
        if args.bundle.stat().st_size > 25_000_000:
            raise ValueError('Oversized bundle')
        if args.output.resolve() == args.bundle.resolve():
            raise ValueError('Output would overwrite source bundle')
        raw = args.bundle.read_bytes(); bundle = json.loads(raw)
        now = datetime.now(timezone.utc)
        evidence = inspect_bundle(bundle, now=now)
        ledger = ReadOnlyLedger(database_url=audit_database_url(args.database_env))
        with ledger.snapshot(), ledger.connect() as db:
            rows = load_primary(db, evidence, cutoff=args.cutoff, season_min=args.season_min)
        report = build_report(bundle, rows, cutoff=args.cutoff, season_min=args.season_min,
            limit=args.last_n_games, now=now)
        report['bundle_sha256'] = hashlib.sha256(raw).hexdigest()
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
        print(json.dumps(dict(mode='read_only', counts=report['counts'])))
    except Exception as exc:
        raise SystemExit(f'CFB history audit unavailable: {type(exc).__name__}') from None


if __name__ == '__main__':
    main()
