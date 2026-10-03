"""Append-only corrected-NFL workload research receipts, separate from frozen scan/ledger."""
from __future__ import annotations

import asyncio
from collections import Counter,defaultdict
from datetime import date,datetime,timedelta,timezone
import hashlib
import json

from sportsbet.ledger import utc_timestamp
from sportsbet.quant import nfl_corrected_workload_shadow as shadow
from sportsbet.quant import nfl_corrected_workload_audit as audit
from sportsbet.quant.history_shadow import load_histories
from sportsbet.quant.shadow_inputs import normalize_source_timestamps

VERSION='nfl-corrected-workload-paper-v1'
MAX_RECEIPT_BYTES=2_000_000
MAX_AUDIT_ROWS=20_000
MAX_SCAN_ROWS=10_000
SCAN_SQL='''SELECT id,payload FROM analytics.predictions WHERE scan_id=$1
    AND payload::jsonb->>'sport'='nfl' ORDER BY id LIMIT $2'''
INSERT_SQL='''INSERT INTO analytics.paper_selections
    (protocol,sport,game_id,player_id,prediction_id,decision_at,valid_until,payload,payload_sha256)
    SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9
    WHERE clock_timestamp()>=$6 AND clock_timestamp()<$7
    ON CONFLICT (protocol,sport,game_id,player_id) DO NOTHING RETURNING prediction_id'''
AUDIT_SQL='''SELECT s.protocol,s.sport,s.game_id,s.player_id,s.prediction_id,
    s.decision_at,s.valid_until,s.recorded_at,s.payload,s.payload_sha256,
    p.payload AS forecast,p.outcome,p.outcome_source,p.outcome_ref,
    p.outcome_observed_at,p.actual_value,p.outcome_evidence
    FROM analytics.paper_selections s JOIN analytics.predictions p ON p.id=s.prediction_id
    WHERE s.protocol=$1 AND s.sport='nfl' ORDER BY s.recorded_at,s.prediction_id
    LIMIT $2'''


def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def earliest(rows):
    """Fix one supported player/game attempt before reading history or outcomes."""
    chosen={}
    for raw in rows:
        row=json.loads(raw['payload'])
        if row.get('sport')!='nfl' or row.get('prop_type') not in shadow.MARKETS:
            continue
        row['prediction_id']=raw['id']
        key=(row['game_id'],row['player_id'])
        candidate=(utc_timestamp(row['captured_at']),raw['id'],row)
        if key not in chosen or candidate[:2]<chosen[key][:2]:
            chosen[key]=candidate
    return [v[2] for v in sorted(chosen.values(),key=lambda v:v[:2])]


async def capture(pool,scan_id):
    """Only previously stored exact offers; no provider, pick or stake operation."""
    if not isinstance(scan_id,str) or len(scan_id)!=32 or any(c not in '0123456789abcdef' for c in scan_id):
        raise ValueError('Invalid scan identity')
    async with pool.acquire() as conn:
        async with conn.transaction(isolation='repeatable_read',readonly=True):
            sources=await conn.fetch(SCAN_SQL,scan_id,MAX_SCAN_ROWS+1,timeout=4)
    if len(sources)>MAX_SCAN_ROWS:
        raise ValueError('Research scan exceeds bounded row count')
    selected=earliest(sources)
    counts=Counter(attempts=len(selected))
    if not selected:
        return dict(status='no_supported_offers',counts=dict(counts))
    now=datetime.now(timezone.utc)
    current=[]
    for row in selected:
        deadline=min(utc_timestamp(row['game_start_time']),
                     utc_timestamp(row['quote_time'])+timedelta(seconds=300))
        if (utc_timestamp(row['captured_at'])<utc_timestamp(shadow.FROZEN_AT)
                or now>=deadline):
            counts['outside_pregame_window']+=1
        else:
            current.append((row,deadline))
    histories={};read_failed=set()
    groups=defaultdict(set)
    for row,_ in current:
        if isinstance(row.get('role_history_shadow'),dict) and row['role_history_shadow'].get('status')=='predicted':
            groups[row['game_date']].add((row['player_id'],row['prop_type']))
    for game_day,wanted in sorted(groups.items()):
        cutoff=date.fromisoformat(game_day)
        players=sorted({player for player,_ in wanted})
        for offset in range(0,len(players),200):
            batch=set(players[offset:offset+200]);chunk={x for x in wanted if x[0] in batch}
            try:
                async with asyncio.timeout(5):
                    records=await load_histories(pool,'nfl',cutoff.year if cutoff.month>=9 else cutoff.year-1,
                                                 cutoff,chunk)
                histories.update({(game_day,*key):value for key,value in normalize_source_timestamps(records).items()})
            except Exception:
                read_failed.update((game_day,*key) for key in chunk)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout='4s'")
            for row,deadline in current:
                key=(row['game_date'],row['player_id'],row['prop_type'])
                result=shadow.shadow_record(row,histories.get(key,[]),
                    unavailable='history_read_failed' if key in read_failed else None)
                counts[result.get('reason','predicted')]+=1
                original={k:v for k,v in row.items() if k!='prediction_id'}
                raw=encode(original)
                body=dict(version=VERSION,forecast_sha256=digest(raw),shadow=result)
                payload=encode(body)
                if len(payload.encode())>MAX_RECEIPT_BYTES:
                    counts['oversize_receipt']+=1
                    continue
                saved=await conn.fetchval(INSERT_SQL,VERSION,'nfl',row['game_id'],row['player_id'],
                    row['prediction_id'],utc_timestamp(row['captured_at']),deadline,payload,digest(payload))
                counts['recorded' if saved else 'late_or_existing']+=1
    return dict(status='captured',counts=dict(counts),model_version=shadow.VERSION,
                source_limitation='targets_not_individually_committed')


def _joined_row(record):
    body=json.loads(record['payload'])
    forecast=json.loads(record['forecast'])
    if (record['protocol']!=VERSION or record['sport']!='nfl'
            or record['payload_sha256']!=digest(record['payload'])
            or body.get('version')!=VERSION or body.get('forecast_sha256')!=digest(encode(forecast))
            or record['game_id']!=forecast['game_id'] or record['player_id']!=forecast['player_id']
            or record['prediction_id'] is None):
        raise ValueError('Invalid paper receipt')
    expected_deadline=min(utc_timestamp(forecast['game_start_time']),
                          utc_timestamp(forecast['quote_time'])+timedelta(seconds=300))
    if (utc_timestamp(record['decision_at'])!=utc_timestamp(forecast['captured_at'])
            or utc_timestamp(record['valid_until'])!=expected_deadline):
        raise ValueError('Invalid paper decision window')
    row=forecast|dict(prediction_id=record['prediction_id'],history_shadow=body['shadow'],
        history_shadow_recorded_at=utc_timestamp(record['recorded_at']).isoformat(),
        outcome=json.loads(record['outcome']) if record['outcome'] is not None else None,
        outcome_source=record['outcome_source'],outcome_ref=record['outcome_ref'],
        outcome_observed_at=record['outcome_observed_at'],actual_value=record['actual_value'],
        outcome_evidence=json.loads(record['outcome_evidence']) if record['outcome_evidence'] else None)
    if (utc_timestamp(record['recorded_at'])>=utc_timestamp(record['valid_until'])
            or utc_timestamp(record['recorded_at'])<utc_timestamp(record['decision_at'])):
        row['history_shadow']={'model_version':shadow.VERSION,'status':'unavailable','reason':'invalid_or_late_recording'}
    return row


async def report(pool):
    async with pool.acquire() as conn:
        async with conn.transaction(isolation='repeatable_read',readonly=True):
            receipts=await conn.fetch(AUDIT_SQL,VERSION,MAX_AUDIT_ROWS+1,timeout=20)
    if len(receipts)>MAX_AUDIT_ROWS:
        raise ValueError('Research receipt audit exceeds bounded row count')
    rows=[];invalid=0
    for receipt in receipts:
        try:rows.append(_joined_row(receipt))
        except (ValueError,KeyError,TypeError):invalid+=1
    result=audit.report_corrected_workload(rows,'nfl')
    result['invalid_paper_receipts']=invalid
    result['paper_receipts']=len(receipts)
    if invalid:
        result['status']='invalid_paper_receipts'
        for market in result['markets'].values():
            if market['status']=='predictive_evidence_supported':
                market['status']='invalid_paper_receipts'
            market['promote']=False
    return result
