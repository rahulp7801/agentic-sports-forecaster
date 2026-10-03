"""Source-replayed descriptive NBA teammate/opponent participation cohorts."""
from datetime import date, datetime
import json
import math
import re

from sportsbet.prop.recent_participation import recent_participation
from sportsbet.ingestion.nba_participation import participation_record
from sportsbet.ingestion.provenance import row_sha256, stat_row_sha256

MAX_IDENTITY_ROWS=1000
METRICS={'points':'points','rebounds':'rebounds','assists':'assists','pra':'(points+rebounds+assists)'}
SOURCE_FIELDS=('source_provider','source_sha256','source_record_sha256','source_observed_at')


def moment(value):
    result=datetime.fromisoformat(value) if isinstance(value,str) else value
    if not isinstance(result,datetime) or result.utcoffset() is None:
        raise ValueError('Participation time requires a timezone')
    return result


def source_proved(row,cutoff):
    return (row['source_provider'] in ('nba','espn')
        and all(isinstance(row[key],str) and re.fullmatch('[0-9a-f]{64}',row[key])
                for key in ('source_sha256','source_record_sha256'))
        and moment(row['source_observed_at'])<=cutoff)


def verified_participant(row,cutoff):
    record=participation_record(row)
    recorded=moment(row['recorded_at'])
    if (not source_proved(row,cutoff) or recorded>cutoff
            or recorded<moment(row['source_observed_at'])
            or record['game_date']>moment(row['source_observed_at']).date()
            or type(row['version_id']) is not int or row['version_id']<=0
            or row_sha256(record)!=row['source_record_sha256']):
        raise ValueError('NBA participation commitment differs from retained row')
    return record


def decoded(value):
    result=json.loads(value) if isinstance(value,str) else value
    if not isinstance(result,dict):raise ValueError('Invalid participation source row')
    return result


def stored(value):
    if isinstance(value,(date,datetime)):return value.isoformat()
    if isinstance(value,dict):return {k:stored(v) for k,v in value.items()}
    if isinstance(value,list):return [stored(v) for v in value]
    return value


async def nba_participation_split(conn,player_id,season,cutoff,prop_type,line,direction,candidate,observed_before):
    if (prop_type not in METRICS or direction not in ('over','under')
            or type(line) not in (int,float) or not math.isfinite(line)):
        return None
    selected_before=observed_before or await conn.fetchval('SELECT clock_timestamp()')
    selected_before=moment(selected_before)
    # Choose each complete player/game version before filtering name, team or
    # game date. A later correction cannot resurrect the older identity.
    identities=await conn.fetch('''WITH versions AS (
        SELECT DISTINCT ON (player_id,game_id) * FROM public.nba_participation_versions
        WHERE source_observed_at<=$4 AND recorded_at<=$4
        ORDER BY player_id,game_id,recorded_at DESC,version_id DESC
        ) SELECT * FROM versions WHERE LOWER(player_name)=LOWER($1)
          AND team_abbreviation=$2 AND game_date<$3 AND season>=$5
        ORDER BY game_date,version_id LIMIT 1001''',candidate['player'],candidate['stat_team'],cutoff,selected_before,season)
    if not identities or len(identities)>MAX_IDENTITY_ROWS:return None
    try:
        proved=[verified_participant(dict(row),selected_before) for row in identities]
        participants={row['player_id'] for row in proved}
        if len(participants)!=1:return None
        participant_id=participants.pop()
        first=min((row['game_date'] for row in proved if row['minutes'] is not None and row['minutes']>0),default=None)
        if first is None:return None
    except (KeyError,ValueError,TypeError):return None
    relation='team_abbreviation' if candidate['relationship']=='teammate' else 'opponent_team'
    column=METRICS[prop_type]
    # Only immutable allowlisted identifiers enter SQL; source cutoffs and IDs
    # remain parameters. A missing proof is unknown participation, never zero.
    rows=await conn.fetch(f'''SELECT to_jsonb(n) AS subject,to_jsonb(p) AS participant
        FROM public.nba_player_gamelogs n
        LEFT JOIN LATERAL (SELECT * FROM public.nba_participation_versions v
            WHERE v.player_id=$5 AND v.game_id=n.game_id
              AND v.source_observed_at<=$6 AND v.recorded_at<=$6
            ORDER BY v.recorded_at DESC,v.version_id DESC LIMIT 1) p ON true
        WHERE n.player_id=$1 AND n.season>=$2 AND n.game_date<$3
          AND n.{relation}=$4 AND n.game_date>=$7
          AND n.source_observed_at<=$6 AND n.source_provider IN ('nba','espn')
          AND n.source_sha256 ~ '^[0-9a-f]{{64}}$'
          AND n.source_record_sha256 ~ '^[0-9a-f]{{64}}$'
          AND {column} IS NOT NULL
        ORDER BY n.game_date DESC,n.game_id DESC LIMIT 40''',
        int(player_id),season,cutoff,candidate['stat_team'],participant_id,selected_before,first)
    if not rows:return None
    cohorts={'active':[],'absent':[],'unknown':[]};receipts=[];seen=set()
    try:
        for item in rows:
            subject=decoded(item['subject'])
            day=date.fromisoformat(subject['game_date']) if isinstance(subject['game_date'],str) else subject['game_date']
            if (subject['player_id']!=int(player_id) or subject['game_id'] in seen
                    or not first<=day<cutoff or not source_proved(subject,selected_before)
                    or stat_row_sha256('nba',subject)!=subject['source_record_sha256']):
                return None
            seen.add(subject['game_id'])
            fields=('points','rebounds','assists') if prop_type=='pra' else (prop_type,)
            values=[subject[field] for field in fields]
            if any(type(value) not in (int,float) or not math.isfinite(value) for value in values):return None
            value=sum(values);label='unknown';participant=None
            if item['participant'] is not None and item['participant']!='null':
                try:
                    participant=decoded(item['participant'])
                    record=verified_participant(participant,selected_before)
                    correct=(record['player_id']==participant_id and record['game_id']==subject['game_id']
                        and record['game_date']==day and record['team_abbreviation']==candidate['stat_team']
                        and ((record['team_abbreviation']==subject['team_abbreviation'])
                             ==(candidate['relationship']=='teammate')))
                    if correct and record['minutes'] is not None:
                        label='active' if record['minutes']>0 else 'absent'
                except (KeyError,ValueError,TypeError):pass
            cohorts[label].append((day,value))
            receipts.append(dict(subject=subject,participant=participant,classification=label))
    except (KeyError,ValueError,TypeError):return None
    def summary(group):
        values=[value for _,value in cohorts[group]]
        hits=sum(value>line if direction=='over' else value<line for value in values)
        return dict(games=len(values),mean=round(sum(values)/len(values),2) if values else None,
            hit_rate=round(hits/len(values),4) if values else None)
    window={'cutoff':cutoff.isoformat()}
    for group,values in cohorts.items():
        window[group]=dict(oldest=min(day for day,_ in values).isoformat(),
                           newest=max(day for day,_ in values).isoformat()) if values else None
    evidence={key:candidate[key] for key in ('player','status','position','team','relationship','unit')}
    return evidence|dict(active=summary('active'),absent=summary('absent'),unknown_games=len(cohorts['unknown']),
        sample_window=window,evidence_version='recorded-participation-v3',source='nba_final_box_scores',
        participation='recorded minutes',recent_window=recent_participation(cohorts,cutoff,line,direction),
        source_rows=stored(receipts),
        identity_refs=[dict(version_id=row['version_id'],source_record_sha256=row['source_record_sha256'],
            recorded_at=moment(row['recorded_at']).isoformat()) for row in identities],
        observed_before=selected_before.isoformat())
