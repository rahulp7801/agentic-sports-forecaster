"""Frozen untraded recent-role candidate using complete corrected NFL history."""
from __future__ import annotations
import base64
from collections import Counter
import csv
from datetime import date,datetime,timezone
from functools import lru_cache
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import math
import zlib

from sportsbet.ingestion.provenance import STAT_FIELDS
from sportsbet.quant.nfl_history_coverage import audit,SNAP_FIELDS
from sportsbet.quant.nfl_recent_role_params import (VERSION,POLICY,FROZEN_AT,SOURCE_SHA256,PRIOR_STRENGTH,
    BASELINE_VERSION,HISTORY_POLICY,MAX_PLAYERS,MAX_ROWS,MAX_INPUT_BYTES,MAX_COMPRESSED_BYTES)
from sportsbet.quant.history_shadow import offer_digest,digest
from sportsbet.ingestion.nfl_supplement_proof import valid_supplement

MARKETS={'nfl':{'receptions':'receptions','rec_yds':'receiving_yards'}}
ARTIFACT_SHA256=digest(dict(version=VERSION,policy=POLICY,frozen_at=FROZEN_AT,sources=SOURCE_SHA256,prior=PRIOR_STRENGTH,baseline=BASELINE_VERSION,
    history_policy=HISTORY_POLICY,scope='unambiguous-pinned-crosswalk-complete-offensive-history',
    maximum_players=MAX_PLAYERS,maximum_rows=MAX_ROWS))
PROVENANCE=('source_provider','source_sha256','source_record_sha256','source_observed_at')
REASONS=frozenset({'unsupported_market','outside_source_scope','history_read_failed','invalid_role_input',
    'incomplete_participation_history','conflicting_recovery','invalid_current_roster','no_current_role_history',
    'insufficient_history','baseline_history_mismatch','outside_prospective_quote_window','unsupported_line',
    'unsupported_baseline','invalid_exact_offer','invalid_or_late_recording','shadow_evaluation_failed'})

@lru_cache(maxsize=1)
def implementation_sha256():
    paths=[Path(__file__).with_name(name) for name in ('nfl_recent_role_shadow.py','nfl_recent_role_params.py','nfl_history_coverage.py')]
    paths += [Path(__file__).parents[1]/'ingestion'/name for name in ('nfl_supplement_proof.py','provenance.py')]
    return digest({path.name:hashlib.sha256(path.read_text(encoding='utf-8-sig').encode()).hexdigest() for path in paths})

@lru_cache(maxsize=1)
def artifact():
    raw=Path(__file__).with_name('nfl_role_sources.json.gz').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:raise ValueError('invalid_role_input')
    bundle=json.loads(gzip.decompress(raw));identity=bundle['identity']
    rows=list(csv.DictReader(io.StringIO(identity['response_text'])))
    counts={key:Counter(r[key] for r in rows) for key in ('gsis_id','pfr_id','espn_id')}
    players={r['gsis_id']:dict(player_id=r['gsis_id'],player=r['display_name'],pfr_player_id=r['pfr_id'],
        espn_player_id=r['espn_id'],current_quoted=True) for r in rows
        if all(counts[key][r[key]]==1 for key in counts)
        and re.fullmatch('00-[0-9]{7}',r['gsis_id']) and re.fullmatch('[A-Za-z0-9]{1,20}',r['pfr_id'])
        and re.fullmatch('[1-9][0-9]*',r['espn_id'])}
    return identity,players


@lru_cache(maxsize=128)
def encoded_inputs(canonical):
    raw=canonical.encode('utf-8')
    if len(raw)>MAX_INPUT_BYTES:raise ValueError('invalid_role_input')
    compressed=gzip.compress(raw,compresslevel=6,mtime=0)
    if len(compressed)>MAX_COMPRESSED_BYTES:raise ValueError('invalid_role_input')
    return dict(encoding='gzip-base64-json-v1',sha256=hashlib.sha256(raw).hexdigest(),
        uncompressed_bytes=len(raw),data=base64.b64encode(compressed).decode('ascii'))


@lru_cache(maxsize=128)
def decoded_inputs(canonical):
    encoded=json.loads(canonical)
    if (encoded['encoding']!='gzip-base64-json-v1' or type(encoded['uncompressed_bytes']) is not int
            or not 0<encoded['uncompressed_bytes']<=MAX_INPUT_BYTES
            or not isinstance(encoded['data'],str) or len(encoded['data'])>4*((MAX_COMPRESSED_BYTES+2)//3)):
        raise ValueError('invalid_role_input')
    compressed=base64.b64decode(encoded['data'],validate=True)
    inflater=zlib.decompressobj(16+zlib.MAX_WBITS)
    raw=inflater.decompress(compressed,MAX_INPUT_BYTES+1)
    if (len(raw)!=encoded['uncompressed_bytes'] or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail
            or hashlib.sha256(raw).hexdigest()!=encoded['sha256']):raise ValueError('invalid_role_input')
    value=json.loads(raw)
    if not isinstance(value,dict):raise ValueError('invalid_role_input')
    return value


async def load_inputs(pool,sport,season,cutoff,requests,*,observed_before):
    if sport!='nfl':return {}
    _,players=artifact();ids=sorted(set(requests)&set(players))
    if not ids:return {}
    if len(ids)>MAX_PLAYERS or observed_before.utcoffset() is None:raise ValueError('invalid_role_input')
    pfr=[players[k]['pfr_player_id'] for k in ids];limit=MAX_ROWS*len(ids)+1
    async with pool.acquire() as conn:
        async with conn.transaction(isolation='repeatable_read',readonly=True):
            stats=await conn.fetch("""SELECT to_jsonb(ps) AS stat,g.game_id,g.game_date,g.home_team,g.away_team
                FROM player_stats ps LEFT JOIN games g ON g.season=ps.season AND g.week=ps.week
                AND ps.team IN (g.home_team,g.away_team) WHERE ps.player_id=ANY($1::text[])
                AND ps.season>=$2 AND ps.season<=$3 AND ps.source_observed_at<=$4
                ORDER BY ps.player_id,ps.season,ps.week LIMIT $5""",ids,season-2,season,observed_before,limit,timeout=4)
            snaps=await conn.fetch("""SELECT to_jsonb(sc)-'id' AS snap,g.game_id,g.game_date,g.home_team,g.away_team
                FROM nfl_snap_counts sc LEFT JOIN games g ON g.game_id=sc.game_id
                WHERE sc.pfr_player_id=ANY($1::text[]) AND sc.season>=$2 AND sc.season<=$3
                AND sc.source_observed_at<=$4
                ORDER BY sc.pfr_player_id,sc.season,sc.week LIMIT $5""",pfr,season-2,season,observed_before,limit,timeout=4)
            supplements=await conn.fetch("""SELECT to_jsonb(s) AS supplement,g.game_date,g.home_team,g.away_team
                FROM nfl_receiving_supplements s LEFT JOIN games g ON g.game_id=s.game_id
                AND g.season=s.season AND g.week=s.week
                WHERE s.player_id=ANY($1::text[]) AND s.season>=$2 AND s.season<=$3
                AND s.observed_at<=$4 AND s.inserted_at<=$4
                ORDER BY s.player_id,s.season,s.week LIMIT $5""",ids,season-2,season,observed_before,limit,timeout=4)
    if any(len(rows)>=limit for rows in (stats,snaps,supplements)):raise ValueError('invalid_role_input')
    now=datetime.now(timezone.utc).isoformat();result={}
    for gsis in ids:
        value=dict(observed_at=now,observed_before=observed_before.isoformat(),cutoff=cutoff.isoformat(),
            season_floor=season-2,players=[players[gsis]],stats=[],snaps=[],supplements=[])
        for kind,records,field,fields in [('stats',stats,'stat',STAT_FIELDS['nfl']),('snaps',snaps,'snap',SNAP_FIELDS)]:
            for item in records:
                raw=item[field];row=json.loads(raw) if isinstance(raw,str) else raw
                if row.get('player_id' if field=='stat' else 'pfr_player_id')!=(gsis if field=='stat' else players[gsis]['pfr_player_id']):continue
                value[kind].append({k:str(item[k]) for k in ('game_id','game_date','home_team','away_team')}|{field:{k:row[k] for k in (*fields,*PROVENANCE)}})
        for item in supplements:
            raw=item['supplement'];row=json.loads(raw) if isinstance(raw,str) else raw
            if row['player_id']==gsis:
                value['supplements'].append(dict(supplement=row,**{k:str(item[k]) for k in ('game_date','home_team','away_team')}))
        if any(len(value[k])>MAX_ROWS for k in ('stats','snaps','supplements')):continue
        result[gsis]=value
    return result


@lru_cache(maxsize=128)
def validated_rows(encoded):
    data=decoded_inputs(encoded);identity,players=artifact()
    if (len(data['players'])!=1 or any(len(data[k])>MAX_ROWS for k in ('stats','snaps','supplements'))):
        raise ValueError('invalid_role_input')
    player,=data['players'];gsis=player['player_id']
    if players.get(gsis)!=player:raise ValueError('outside_source_scope')
    from sportsbet.ledger import utc_timestamp
    cutoff=utc_timestamp(data['observed_before'])
    if cutoff>utc_timestamp(data['observed_at']):raise ValueError('invalid_role_input')
    coverage=audit(data|{'identity':identity},now=utc_timestamp(data['observed_at']))
    if utc_timestamp(identity['retrieved_at'])>cutoff:raise ValueError('invalid_role_input')
    for kind,key in (('stats','stat'),('snaps','snap')):
        if any(utc_timestamp(item[key]['source_observed_at'])>cutoff for item in data[kind]):raise ValueError('invalid_role_input')
    merged={}
    for item in data['stats']:
        row=item['stat']
        if row['season']>=data['season_floor'] and item['game_date']<data['cutoff']:
            merged[(row['season'],row['week'])]=dict(row,day=item['game_date'])
    added=0;seen=set()
    for item in data['supplements']:
        s=item['supplement'];row=s['stat_row'];key=(s['season'],s['week']);m=s['manifest'];game=m['game']
        if (key in seen or s['player_id']!=gsis or row['player_id']!=gsis
                or any(row[k]!=s[k] for k in ('season','week'))
                or not valid_supplement(row,m,s['source_sha256'],s['observed_at'],game)
                or s['stat_record_sha256']!=m['stat_record_sha256'] or s['bundle_sha256']!=m['bundle_sha256']
                or s['game_id']!=m['explicit_source']['participation']['row']['game_id']
                or any(item[k]!=m['explicit_source']['participation'][k] for k in ('game_date','home_team','away_team'))
                or max(utc_timestamp(s['observed_at']),utc_timestamp(s['inserted_at']))>cutoff):
            raise ValueError('invalid_role_input')
        seen.add(key)
        if s['season']<data['season_floor'] or item['game_date']>=data['cutoff']:continue
        if key in merged:
            if any(merged[key][k]!=row[k] for k in ('team','receiving_yards','receptions')):raise ValueError('conflicting_recovery')
        else:merged[key]=dict(row,day=item['game_date']);added+=1
    if any((r['season'],r['week']) not in merged for r in coverage['missing_games']):raise ValueError('incomplete_participation_history')
    participation={(s['snap']['season'],s['snap']['week']):s['snap'] for s in data['snaps'] if s['game_date']<data['cutoff']}
    if any(key not in participation or participation[key]['offense_snaps']<=0 for key in merged):raise ValueError('incomplete_participation_history')
    rows=sorted(merged.values(),key=lambda r:(r['season'],r['week']))[-40:]
    if not 20<=len(rows)<=40:raise ValueError('insufficient_history')
    if any(type(r.get(k)) is not int or abs(r[k])>10000 or (k=='receptions' and r[k]<0)
           for r in rows for k in ('receiving_yards','receptions')):raise ValueError('invalid_role_input')
    return rows,added


def probability(rows,stat,line,season,team):
    current=[r for r in rows if r['season']==season and r['team']==team]
    older=[r for r in rows if r not in current]
    if not current:raise ValueError('no_current_role_history')
    prior=(sum(r[stat]>line for r in older)+.5)/(len(older)+1)
    p=(sum(r[stat]>line for r in current)+PRIOR_STRENGTH*prior)/(len(current)+PRIOR_STRENGTH)
    return p,dict(sample_size=len(rows),current_role_games=len(current),older_games=len(older),
        older_over_probability=prior,corrected_baseline_over_probability=(sum(r[stat]>line for r in rows)+.5)/(len(rows)+1))


def _offer(payload):
    from sportsbet.ledger import quote_evidence_valid,settlement_identity_valid,utc_timestamp
    now=utc_timestamp(payload['captured_at']);line=float(payload['line'])
    if not math.isfinite(line) or line<.5 or not (line*2).is_integer() or line.is_integer():raise ValueError('unsupported_line')
    if (payload['model_version']!=BASELINE_VERSION or payload.get('history_policy_version')!=HISTORY_POLICY
            or payload['direction'] not in ('over','under') or payload.get('forecast_cutoff')!=payload['game_date']
            or type(payload.get('push_probability')) not in (int,float) or payload['push_probability']!=0
            or any(type(payload.get(k)) not in (int,float) or not math.isfinite(payload[k]) for k in ('model_probability','model_mean_stat'))):raise ValueError('unsupported_baseline')
    if not quote_evidence_valid(payload) or not settlement_identity_valid(payload):raise ValueError('invalid_exact_offer')
    if (not utc_timestamp(FROZEN_AT)<=now<utc_timestamp(payload['game_start_time'])
            or not 0<=(now-utc_timestamp(payload['quote_time'])).total_seconds()<=300
            or utc_timestamp(payload['model_generated_at'])!=now):raise ValueError('outside_prospective_quote_window')
    return now,line


def shadow_record(payload,inputs,*,unavailable=None):
    from sportsbet.ledger import utc_timestamp
    result=dict(model_version=VERSION,policy_version=POLICY,artifact_sha256=ARTIFACT_SHA256,
        implementation_sha256=implementation_sha256(),generated_at=payload.get('captured_at'),status='unavailable')
    try:
        if payload.get('sport')!='nfl' or payload.get('prop_type') not in MARKETS['nfl']:raise ValueError('unsupported_market')
        if payload['player_id'] not in artifact()[1]:raise ValueError('outside_source_scope')
        if unavailable:raise ValueError(unavailable)
        now,line=_offer(payload)
        result['generated_at']=now.isoformat()
        if len(inputs['players'])!=1 or inputs['players'][0]['player_id']!=payload['player_id'] or any(len(inputs[k])>MAX_ROWS for k in ('stats','snaps','supplements')):raise ValueError('invalid_role_input')
        if now<utc_timestamp(FROZEN_AT) or not 0<=(now-utc_timestamp(inputs['observed_at'])).total_seconds()<=300:raise ValueError('outside_prospective_quote_window')
        if inputs['cutoff']!=payload['game_date'] or utc_timestamp(inputs['observed_before'])!=utc_timestamp(payload['history_observed_before']):raise ValueError('invalid_role_input')
        target=date.fromisoformat(payload['game_date']);season=target.year if target.month>=9 else target.year-1
        if inputs['season_floor']!=season-2:raise ValueError('invalid_role_input')
        a=payload.get('availability',{});binding=artifact()[1][payload['player_id']]
        if (a.get('status')!='observed' or a.get('roster_confirmed') is not True
                or a.get('player_id')!=binding['espn_player_id'] or not re.fullmatch('[A-Z]{2,3}',a.get('team',''))
                or not 0<=(now-utc_timestamp(a['captured_at'])).total_seconds()<=3600
                or not re.fullmatch('[0-9a-f]{64}',a.get('roster_source_sha256',''))
                or not re.fullmatch(r'https://site\.api\.espn\.com/apis/site/v2/sports/football/nfl/teams/[1-9][0-9]*/roster',a.get('roster_source_url',''))):raise ValueError('invalid_current_roster')
        encoded=encoded_inputs(json.dumps(inputs,sort_keys=True,separators=(',',':'),allow_nan=False))
        merged,added=validated_rows(json.dumps(encoded,sort_keys=True,separators=(',',':')))
        stat=MARKETS['nfl'][payload['prop_type']];baseline=merged
        p_base=(sum(r[stat]>line for r in baseline)+.5)/(len(baseline)+1)
        if not baseline or payload.get('model_mean_stat') is None or abs(float(payload['model_mean_stat'])-sum(r[stat] for r in baseline)/len(baseline))>.005001:raise ValueError('baseline_history_mismatch')
        if payload['model_sample_size']!=len(baseline) or abs(float(payload['model_probability'])-(p_base if payload['direction']=='over' else 1-p_base))>1e-6:raise ValueError('baseline_history_mismatch')
        p,counts=probability(merged,stat,line,season,{'LAR':'LA','WSH':'WAS'}.get(a['team'],a['team']))
        result.update(status='predicted',probability=p if payload['direction']=='over' else 1-p,
            counts=counts,recovered_games=added,inputs=encoded,offer_sha256=offer_digest(payload),availability_sha256=digest(a))
        result['record_sha256']=digest(result)
    except (KeyError,TypeError,ValueError,ArithmeticError) as exc:
        result.update(status='unavailable',reason=str(exc) if str(exc) in REASONS else 'invalid_role_input')
    return result


def verified_shadow_probability(payload):
    try:
        record=payload['role_history_shadow']
        if record.get('status')!='predicted':return None
        expected=shadow_record(payload,decoded_inputs(json.dumps(record['inputs'],sort_keys=True,separators=(',',':'))))
        return record['probability'] if digest(expected)==digest(record) else None
    except Exception:return None


def verified_recorded_shadow_probability(payload):
    from sportsbet.ledger import utc_timestamp
    try:
        receipt=utc_timestamp(payload['role_history_shadow_recorded_at'])
        if not utc_timestamp(payload['captured_at'])<=receipt<utc_timestamp(payload['game_start_time']) or not 0<=(receipt-utc_timestamp(payload['quote_time'])).total_seconds()<=300:return None
        return verified_shadow_probability(payload)
    except Exception:return None
