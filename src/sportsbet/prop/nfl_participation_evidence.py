"""Replay the exact source rows used by descriptive NFL participation cohorts.

This is not a model or qualification rule. One SQL snapshot retains the target,
tenure and participation receipts; Python verifies commitments before describing
them. Frozen result hashes and research evaluators remain unchanged.
"""
from datetime import date, datetime
import json
import math
import re

from sportsbet.prop.recent_participation import recent_participation
from sportsbet.ingestion.nfl_supplement_proof import valid_supplement
from sportsbet.ingestion.provenance import STAT_FIELDS, row_sha256, stat_row_sha256

METRICS={'pass_yds':'passing_yards','rush_yds':'rushing_yards',
         'rec_yds':'receiving_yards','receptions':'receptions'}
SNAP_FIELDS=('game_id','season','week','player_name','pfr_player_id','position',
             'team','opponent','offense_snaps','defense_snaps')
PROVENANCE=('source_provider','source_sha256','source_record_sha256','source_observed_at')
GAME_FIELDS=('game_id','season','week','game_date','home_team','away_team')


def moment(value):
    result=datetime.fromisoformat(value) if isinstance(value,str) else value
    if not isinstance(result,datetime) or result.utcoffset() is None:
        raise ValueError('NFL context requires an aware source receipt')
    return result


def decoded(value):
    return json.loads(value) if isinstance(value,str) else value


def stored(value):
    if isinstance(value,(datetime,date)):return value.isoformat()
    if isinstance(value,dict):return {k:stored(v) for k,v in value.items()}
    if isinstance(value,list):return [stored(v) for v in value]
    return value


def retained(item,*,tenure=False):
    """Keep proof inputs, without duplicating unrelated game/stat payloads."""
    game={key:item['game'][key] for key in GAME_FIELDS}
    def snap_receipt(row):
        return {key:row[key] for key in (*SNAP_FIELDS,*PROVENANCE) if key in row} if isinstance(row,dict) else row
    if tenure:return dict(game=game,snap=snap_receipt(item['snap']))
    stat=item['stat'];fields=(*STAT_FIELDS['nfl'],*PROVENANCE)
    if stat['source_provider']=='nflverse_espn_supplement':
        fields+=('supplement_manifest','supplement_inserted_at')
    return dict(game=game,stat={key:stat[key] for key in fields},
        snaps=[snap_receipt(row) for row in item['snaps']])


def game_identity(game,row,cutoff,selected_before):
    day=date.fromisoformat(game['game_date']) if isinstance(game['game_date'],str) else game['game_date']
    home,away=game['home_team'],game['away_team']
    if (type(row['season']) is not int or not 2000<=row['season']<=2100
            or type(row['week']) is not int or not 1<=row['week']<=18
            or (row['season'],row['week'])!=(game['season'],game['week'])
            or any(not isinstance(t,str) or not re.fullmatch('[A-Z]{2,3}',t) for t in (home,away))
            or home==away or row['team'] not in (home,away)
            or game['game_id']!=f"{row['season']}_{row['week']:02}_{away}_{home}"
            or type(day) is not date or not date(row['season'],7,1)<=day<=date(row['season']+1,6,30)
            or day>=cutoff or not day<=moment(row['source_observed_at']).date()
            or moment(row['source_observed_at'])>selected_before
            or any(not isinstance(row[k],str) or not re.fullmatch('[0-9a-f]{64}',row[k])
                   for k in ('source_sha256','source_record_sha256'))):
        raise ValueError('NFL context source does not match a prior game')
    return day,away if row['team']==home else home


def verify_snap(snap,game,candidate,cutoff,selected_before):
    day,opponent=game_identity(game,snap,cutoff,selected_before)
    if (snap['source_provider']!='nflverse' or snap['pfr_player_id']!=candidate['participant_id']
            or snap['team']!=candidate['stat_team'] or snap['opponent']!=opponent
            or snap['game_id']!=game['game_id']
            or any(type(snap[k]) is not int or not 0<=snap[k]<=32767
                   for k in ('offense_snaps','defense_snaps'))
            or row_sha256({k:snap[k] for k in SNAP_FIELDS})!=snap['source_record_sha256']):
        raise ValueError('NFL context participation commitment differs from its row')
    return day


def verify_target(stat,game,player_id,prop,cutoff,selected_before):
    day,opponent=game_identity(game,stat,cutoff,selected_before)
    value=stat[METRICS[prop]]
    if stat['player_id']!=player_id or type(value) is not int:
        raise ValueError('NFL context target identity or value differs')
    current=stat_row_sha256('nfl',stat)
    allowed={current}
    if prop!='receptions':allowed.add(stat_row_sha256('nfl',stat,legacy_nfl=True))
    if stat['source_record_sha256'] not in allowed:
        raise ValueError('NFL context target commitment differs from its row')
    if stat['source_provider']=='nflverse':return day,opponent,value
    if stat['source_provider']!='nflverse_espn_supplement' or prop not in ('rec_yds','receptions'):
        raise ValueError('Unsupported NFL context provider')
    manifest=stat['supplement_manifest'];final=manifest['game']
    aliases={'LAR':'LA','WSH':'WAS'}
    if (moment(stat['supplement_inserted_at'])>selected_before
            or final['date']!=day.isoformat()
            or aliases.get(final['home_abbr'],final['home_abbr'])!=game['home_team']
            or aliases.get(final['away_abbr'],final['away_abbr'])!=game['away_team']
            or not valid_supplement(stat,manifest,stat['source_sha256'],stat['source_observed_at'],final)):
        raise ValueError('NFL receiving context supplement is unproved')
    return day,opponent,value


async def nfl_participation_split(conn,player_id,season,cutoff,prop,line,direction,candidate,observed_before):
    if (prop not in METRICS or direction not in ('over','under')
            or type(line) not in (int,float) or not math.isfinite(line)):
        return None
    from sportsbet.model_contract import NFL_HISTORY_FROZEN_AT
    corrected=(prop in ('rec_yds','receptions') and observed_before is not None
        and observed_before>=datetime.fromisoformat(NFL_HISTORY_FROZEN_AT))
    table='nfl_effective_receiving_gamelogs' if corrected else 'player_stats'
    column=METRICS[prop]
    snap_column='offense_snaps' if candidate['unit']=='offense' else 'defense_snaps'
    relation='ps.team=$4' if candidate['relationship']=='teammate' else '(CASE WHEN ps.team=g.home_team THEN g.away_team ELSE g.home_team END)=$4'
    inserted='AND (ps.supplement_inserted_at IS NULL OR ps.supplement_inserted_at<=(SELECT observed_before FROM decision))' if corrected else ''
    # Only static table/column/relation fragments enter SQL. Every identity,
    # date, season and observation cutoff is a parameter. A single statement
    # prevents a source correction racing a second proof query.
    result=await conn.fetchrow(f'''WITH decision AS (
        SELECT COALESCE($6::timestamptz,clock_timestamp()) AS observed_before
    ), tenure_rows AS (
        SELECT sc.season,sc.week,to_jsonb(sc)-'id' AS snap,to_jsonb(g) AS game
        FROM nfl_snap_counts sc JOIN games g ON g.game_id=sc.game_id
        WHERE sc.pfr_player_id=$5 AND sc.team=$4 AND sc.{snap_column}>0
          AND sc.season>=$2 AND g.game_date<$3
          AND sc.source_provider='nflverse'
          AND sc.source_observed_at<=(SELECT observed_before FROM decision)
        ORDER BY sc.season,sc.week,sc.game_id LIMIT 1001
    ), tenure AS (SELECT MIN(season*100+week) AS first_week FROM tenure_rows), target AS (
        SELECT to_jsonb(ps) AS stat,to_jsonb(g) AS game,
          (SELECT COALESCE(jsonb_agg(to_jsonb(sc)-'id'),'[]'::jsonb)
             FROM nfl_snap_counts sc WHERE sc.season=ps.season AND sc.week=ps.week
               AND sc.team=$4 AND sc.pfr_player_id=$5
               AND sc.source_observed_at<=(SELECT observed_before FROM decision)) AS snaps
        FROM {table} ps JOIN games g ON g.season=ps.season AND g.week=ps.week
          AND ps.team IN (g.home_team,g.away_team)
        WHERE ps.player_id=$1 AND ps.season>=$2 AND ps.{column} IS NOT NULL
          AND g.game_date<$3 AND {relation}
          AND (SELECT COUNT(*) FROM games j WHERE j.season=ps.season AND j.week=ps.week
               AND ps.team IN (j.home_team,j.away_team))=1
          AND ps.source_observed_at<=(SELECT observed_before FROM decision) {inserted}
          AND ps.season*100+ps.week>=(SELECT first_week FROM tenure)
        ORDER BY ps.season DESC,ps.week DESC LIMIT 40
    ) SELECT (SELECT observed_before FROM decision) AS observed_before,
        (SELECT jsonb_agg(to_jsonb(t)) FROM tenure_rows t) AS tenure_rows,
        jsonb_agg(to_jsonb(target)) AS source_rows FROM target''',
        player_id,season,cutoff,candidate['stat_team'],candidate['participant_id'],observed_before)
    try:
        selected_before=moment(result['observed_before'])
        tenure=decoded(result['tenure_rows']);rows=decoded(result['source_rows'])
        if not isinstance(tenure,list) or not 0<len(tenure)<=1000 or not isinstance(rows,list) or not 0<len(rows)<=40:return None
        seen=set()
        for item in tenure:
            verify_snap(item['snap'],item['game'],candidate,cutoff,selected_before)
            key=(item['snap']['season'],item['snap']['week'])
            if key in seen:return None
            seen.add(key)
        cohorts={'active':[],'absent':[],'unknown':[]};receipts=[];seen=set()
        for item in rows:
            stat,game,snaps=item['stat'],item['game'],item['snaps']
            day,opponent,value=verify_target(stat,game,player_id,prop,cutoff,selected_before)
            if (stat['season']<season or game['game_id'] in seen
                    or (stat['team'] if candidate['relationship']=='teammate' else opponent)!=candidate['stat_team']):return None
            seen.add(game['game_id']);label='unknown'
            if len(snaps)==1:
                # Zero NFL snaps can be a legacy null-fill. Even a valid zero
                # commitment does not prove an absence; it stays unknown.
                try:
                    verify_snap(snaps[0],game,candidate,cutoff,selected_before)
                    if snaps[0][snap_column]>0:label='active'
                except (KeyError,ValueError,TypeError):pass
            cohorts[label].append((day,value));receipts.append(retained(item)|{'classification':label})
    except (KeyError,ValueError,TypeError,ArithmeticError):return None
    active=cohorts['active'];values=[v for _,v in active]
    hits=sum(v>line if direction=='over' else v<line for v in values)
    window={'cutoff':cutoff.isoformat(),'absent':None}
    for group,items in cohorts.items():
        window[group]=dict(oldest=min(d for d,_ in items).isoformat(),newest=max(d for d,_ in items).isoformat()) if items else None
    evidence={key:candidate[key] for key in ('player','status','position','team','relationship','unit')}
    return evidence|dict(active=dict(games=len(active),mean=round(sum(values)/len(values),2) if values else None,
        hit_rate=round(hits/len(values),4) if values else None),absent=dict(games=0,mean=None,hit_rate=None),
        unknown_games=len(cohorts['unknown']),sample_window=window,evidence_version='recorded-participation-v3',
        source='nflverse_snap_counts',participation='recorded unit snaps',
        recent_window=recent_participation(cohorts,cutoff,line,direction),source_rows=stored(receipts),
        tenure_rows=stored([retained(item,tenure=True) for item in tenure]),observed_before=selected_before.isoformat())
