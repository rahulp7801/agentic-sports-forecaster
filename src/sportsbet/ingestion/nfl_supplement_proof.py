"""Verify retained NFL receiving supplement commitments and exact game identity."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import re
from sportsbet.ingestion.provenance import stat_row_sha256, row_sha256

PROVIDER = 'nflverse_espn_supplement'
POLICY = 'nfl-explicit-receiving-v1'


def _sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _time(value):
    result = value if isinstance(value,datetime) else datetime.fromisoformat(value)
    if result.utcoffset() is None: raise ValueError('Aware receipt required')
    return result.astimezone(timezone.utc)


def valid_supplement(row, manifest, source_sha256, observed_at, game):
    try:
        if (not isinstance(manifest,dict) or manifest.get('version')!=1
                or manifest.get('policy_version')!=POLICY or _sha(manifest)!=source_sha256
                or not re.fullmatch('[0-9a-f]{64}',manifest['bundle_sha256'])
                or stat_row_sha256('nfl',row)!=manifest['stat_record_sha256']): return False
        final=manifest['game'];explicit=manifest['explicit_source']
        if (any(final[k]!=game[k] for k in ('provider_event_id','date','home_abbr','away_abbr'))
                or _time(final['game_time'])!=_time(game['game_time']) or final['completed'] is not True
                or explicit['version']!=1 or explicit['gsis_player_id']!=row['player_id']
                or explicit['did_not_play'] is not False or explicit['games_played']!=1
                or _sha(explicit)!=manifest['explicit_source_sha256']
                or explicit['identity_source_url']!='https://github.com/nflverse/nflverse-data/releases/download/players/players.csv'
                or not re.fullmatch('[0-9a-f]{64}',explicit['identity_source_sha256'])): return False
        if (row['passing_yards'] is not None or row['rushing_yards'] is not None
                or type(row['receptions']) is not int or not 0<=row['receptions']<=10000
                or type(row['receiving_yards']) is not int or abs(row['receiving_yards'])>10000
                or (row['receptions']==0 and row['receiving_yards']!=0)): return False
        start=_time(final['game_time']);observed=_time(observed_at)
        event=final['provider_event_id'];athlete=explicit['espn_player_id']
        if not re.fullmatch('[1-9][0-9]*',event) or not re.fullmatch('[1-9][0-9]*',athlete):return False
        summary,home,away,stats=explicit['sources']
        root='https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/'+event+'/competitions/'+event+'/competitors/'
        if summary['url']!='https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event='+event:return False
        roster_ids=[]
        for source in (home,away):
            match=re.fullmatch(re.escape(root)+r'([1-9][0-9]*)/roster\?limit=100',source['url'])
            if not match:return False
            roster_ids.append(match[1])
        if roster_ids[0]==roster_ids[1] or not any(stats['url'] in (
                root+tid+'/roster/'+athlete+'/statistics/0',
                root+tid+'/roster/'+athlete+'/statistics/0?lang=en&region=us') for tid in roster_ids):return False
        if any(not re.fullmatch('[0-9a-f]{64}',source['sha256'])
               or not start<=_time(summary['observed_at'])<=_time(source['observed_at'])<=observed
               for source in (summary,home,away,stats)):return False
        participation=explicit['participation'];snap=participation['row']
        home_team={'LAR':'LA','WSH':'WAS'}.get(final['home_abbr'],final['home_abbr'])
        away_team={'LAR':'LA','WSH':'WAS'}.get(final['away_abbr'],final['away_abbr'])
        if (participation['source_provider']!='nflverse'
                or not re.fullmatch('[0-9a-f]{64}',participation['source_sha256'])
                or row_sha256(snap)!=participation['source_record_sha256']
                or not start<=_time(participation['source_observed_at'])<=observed
                or snap['pfr_player_id']!=explicit['pfr_player_id']
                or any(snap[k]!=row[k] for k in ('season','week','team'))
                or snap['game_id']!=f"{row['season']}_{row['week']:02}_{away_team}_{home_team}"
                or {snap['team'],snap['opponent']}!={home_team,away_team}
                or type(snap['offense_snaps']) is not int or snap['offense_snaps']<=0
                or participation['game_date']!=final['date']
                or participation['home_team']!=home_team or participation['away_team']!=away_team):return False
        return True
    except (ArithmeticError,KeyError,TypeError,ValueError):
        return False
