"""Append-only stat-only NFL research receipts from saved scans; no quote collection."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json

from sportsbet.ledger import utc_timestamp
from sportsbet.quant import nfl_stat_only_shadow as shadow
from sportsbet.quant import nfl_stat_only_audit as audit

VERSION = 'nfl-stat-only-paper-v1'
PROTOCOLS = {prop: VERSION+':'+prop for prop in shadow.MARKETS}
MAX_SCAN_ROWS = 10_000
MAX_AUDIT_ROWS = 20_000
MAX_RECEIPT_BYTES = 2_000_000
SCAN_SQL = '''SELECT id,payload FROM analytics.predictions WHERE scan_id=$1
    AND payload::jsonb->>'sport'='nfl' ORDER BY id LIMIT $2'''
EVENT_SCAN_SQL = '''SELECT id,payload FROM analytics.predictions WHERE scan_id=$1
    AND payload::jsonb->>'sport'='nfl' AND payload::jsonb->>'game_id'=$3
    ORDER BY id LIMIT $2'''
INSERT_SQL = '''INSERT INTO analytics.paper_selections
    (protocol,sport,game_id,player_id,prediction_id,decision_at,valid_until,payload,payload_sha256)
    SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9
    WHERE clock_timestamp()>=$6 AND clock_timestamp()<$7
    ON CONFLICT (protocol,sport,game_id,player_id) DO NOTHING RETURNING prediction_id'''
AUDIT_SQL = '''SELECT s.protocol,s.sport,s.game_id,s.player_id,s.prediction_id,
    s.decision_at,s.valid_until,s.recorded_at,s.payload,s.payload_sha256,
    p.payload AS forecast,p.outcome,p.outcome_source,p.outcome_ref,
    p.outcome_observed_at,p.actual_value,p.outcome_evidence
    FROM analytics.paper_selections s JOIN analytics.predictions p ON p.id=s.prediction_id
    WHERE s.protocol=ANY($1::text[]) AND s.sport='nfl'
    ORDER BY s.recorded_at,s.prediction_id LIMIT $2'''


def encode(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def earliest(rows: list[dict]) -> list[dict]:
    """Fix one player/game/prop attempt before source, prediction or outcome filtering."""
    chosen = {}
    for raw in rows:
        row = json.loads(raw['payload'])
        if row.get('sport') != 'nfl' or row.get('prop_type') not in shadow.MARKETS:
            continue
        row['prediction_id'] = raw['id']
        key = (row['game_id'], row['player_id'], row['prop_type'])
        candidate = (utc_timestamp(row['captured_at']), str(raw['id']), row)
        if key not in chosen or candidate[:2] < chosen[key][:2]:
            chosen[key] = candidate
    return [value[2] for value in sorted(chosen.values(), key=lambda value: value[:2])]


async def capture(pool, scan_id: str, event_id: str | None = None) -> dict:
    if (not isinstance(scan_id, str) or len(scan_id) != 32
            or any(c not in '0123456789abcdef' for c in scan_id)):
        raise ValueError('Invalid scan identity')
    if event_id is not None and (not isinstance(event_id, str) or not 0 < len(event_id) <= 100):
        raise ValueError('Invalid paper event identity')
    async with pool.acquire() as conn:
        async with conn.transaction(isolation='repeatable_read', readonly=True):
            if event_id is None:
                sources = await conn.fetch(SCAN_SQL, scan_id, MAX_SCAN_ROWS+1, timeout=4)
            else:
                sources = await conn.fetch(EVENT_SCAN_SQL, scan_id, MAX_SCAN_ROWS+1,
                                           event_id, timeout=4)
    if len(sources) > MAX_SCAN_ROWS:
        raise ValueError('Research scan exceeds bounded row count')
    selected = earliest(sources)
    counts = Counter(attempts=len(selected))
    if not selected:
        return dict(status='no_supported_offers', counts=dict(counts))
    now = datetime.now(timezone.utc)
    current = []
    for row in selected:
        deadline = min(utc_timestamp(row['game_start_time']),
                       utc_timestamp(row['quote_time'])+timedelta(seconds=300))
        if utc_timestamp(row['captured_at']) < utc_timestamp(shadow.FROZEN_AT) or now >= deadline:
            counts['outside_pregame_window'] += 1
        else:
            current.append((row, deadline))
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout='4s'")
            for row, deadline in current:
                result = shadow.shadow_record(row)
                counts[result.get('reason', 'predicted')] += 1
                original = {key: value for key, value in row.items() if key != 'prediction_id'}
                body = dict(version=VERSION, protocol=PROTOCOLS[row['prop_type']],
                            forecast_sha256=digest(encode(original)), shadow=result)
                payload = encode(body)
                if len(payload.encode()) > MAX_RECEIPT_BYTES:
                    counts['oversize_receipt'] += 1
                    continue
                saved = await conn.fetchval(
                    INSERT_SQL, PROTOCOLS[row['prop_type']], 'nfl', row['game_id'],
                    row['player_id'], row['prediction_id'],
                    utc_timestamp(row['captured_at']), deadline, payload, digest(payload))
                counts['recorded' if saved else 'late_or_existing'] += 1
    return dict(status='captured', counts=dict(counts), model_version=shadow.VERSION,
                source_basis='existing_recorded_corrected_role_receipt')


def _joined_row(record: dict) -> dict:
    body = json.loads(record['payload'])
    forecast = json.loads(record['forecast'])
    prop = forecast.get('prop_type')
    if (prop not in PROTOCOLS or not isinstance(body.get('shadow'), dict)
            or record['protocol'] != PROTOCOLS[prop]
            or record['sport'] != 'nfl'
            or record['payload_sha256'] != digest(record['payload'])
            or body.get('version') != VERSION or body.get('protocol') != record['protocol']
            or body.get('forecast_sha256') != digest(encode(forecast))
            or record['game_id'] != forecast['game_id']
            or record['player_id'] != forecast['player_id']
            or record['prediction_id'] is None):
        raise ValueError('Invalid paper receipt')
    expected_deadline = min(utc_timestamp(forecast['game_start_time']),
                            utc_timestamp(forecast['quote_time'])+timedelta(seconds=300))
    if (utc_timestamp(record['decision_at']) != utc_timestamp(forecast['captured_at'])
            or utc_timestamp(record['valid_until']) != expected_deadline):
        raise ValueError('Invalid paper decision window')
    result = forecast | dict(
        prediction_id=record['prediction_id'], stat_only_shadow=body['shadow'],
        stat_only_shadow_recorded_at=utc_timestamp(record['recorded_at']).isoformat(),
        outcome=json.loads(record['outcome']) if record['outcome'] is not None else None,
        outcome_source=record['outcome_source'], outcome_ref=record['outcome_ref'],
        outcome_observed_at=record['outcome_observed_at'], actual_value=record['actual_value'],
        outcome_evidence=json.loads(record['outcome_evidence']) if record['outcome_evidence'] else None)
    if (utc_timestamp(record['recorded_at']) >= utc_timestamp(record['valid_until'])
            or utc_timestamp(record['recorded_at']) < utc_timestamp(record['decision_at'])):
        result['stat_only_shadow'] = dict(model_version=shadow.VERSION, status='unavailable',
                                          reason='invalid_or_late_recording')
    return result


async def report(pool) -> dict:
    async with pool.acquire() as conn:
        async with conn.transaction(isolation='repeatable_read', readonly=True):
            receipts = await conn.fetch(AUDIT_SQL, sorted(PROTOCOLS.values()), MAX_AUDIT_ROWS+1, timeout=20)
    if len(receipts) > MAX_AUDIT_ROWS:
        raise ValueError('Research receipt audit exceeds bounded row count')
    rows = []
    invalid = 0
    for receipt in receipts:
        try:
            rows.append(_joined_row(receipt))
        except (ValueError, KeyError, TypeError, ArithmeticError):
            invalid += 1
    result = audit.report_stat_only(rows)
    result['invalid_paper_receipts'] = invalid
    result['paper_receipts'] = len(receipts)
    if invalid:
        result['status'] = 'invalid_paper_receipts'
        for market in result['markets'].values():
            if market['status'] == 'prospective_probability_support':
                market['status'] = 'invalid_paper_receipts'
            market['promote'] = False
    return result
