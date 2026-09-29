"""Reproduce composite CFB stat commitments without trusting an unhashed overlay."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import re
from sportsbet.ingestion.provenance import STAT_FIELDS, stat_row_sha256

PROVIDER = 'sportsdataverse_espn_supplement'
POLICY = 'cfb-explicit-receiving-v1'


def _sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
        ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _time(value):
    parsed = value if isinstance(value,datetime) else datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError('Observation time requires a timezone')
    return parsed.astimezone(timezone.utc)


def valid_supplement(row, manifest, source_sha256, observed_at, game_time):
    try:
        if (not isinstance(manifest,dict) or manifest.get('version')!=1
                or manifest.get('policy_version')!=POLICY or _sha(manifest)!=source_sha256):
            return False
        for key in ('bundle_sha256','primary_record_sha256','primary_source_sha256',
                'primary_player_sha256','primary_schedule_sha256','explicit_source_sha256',
                'effective_record_sha256'):
            if not isinstance(manifest.get(key),str) or not re.fullmatch('[0-9a-f]{64}',manifest[key]):
                return False
        fields = manifest['supplemented_fields']
        if not isinstance(fields,dict) or not fields or not set(fields)<= {'receiving_yards','receptions'}:
            return False
        if any(type(value) is not int or abs(value)>10000 or row[key]!=value for key,value in fields.items()):
            return False
        if type(row['receptions']) is not int or row['receptions']<0 or (row['receptions']==0 and row['receiving_yards']!=0):
            return False
        original = {k:row[k] for k in STAT_FIELDS['cfb']}
        original.update({k:None for k in fields})
        if (stat_row_sha256('cfb',original)!=manifest['primary_record_sha256']
                or stat_row_sha256('cfb',row)!=manifest['effective_record_sha256']
                or _sha(dict(player=manifest['primary_player_sha256'],schedule=manifest['primary_schedule_sha256']))!=manifest['primary_source_sha256']):
            return False
        explicit = manifest['explicit_source']
        if (not isinstance(explicit,dict) or _sha(explicit)!=manifest['explicit_source_sha256']
                or explicit.get('version')!=1 or explicit.get('kind')!='cfb_explicit_receiving_game_log'
                or explicit.get('athlete_id')!=str(row['athlete_id']) or explicit.get('event_id')!=str(row['game_id'])):
            return False
        final, gamelog = explicit['sources']
        if (final['url']!='https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event='+str(row['game_id'])
                or gamelog['url']!='https://site.web.api.espn.com/apis/common/v3/sports/football/college-football/athletes/'+str(row['athlete_id'])+'/gamelog?season='+str(row['season'])
                or any(not isinstance(r.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',r['sha256']) for r in (final,gamelog))):
            return False
        start, observed = _time(game_time), _time(observed_at)
        final_time, game_time = _time(final['observed_at']), _time(gamelog['observed_at'])
        primary_time = _time(manifest['primary_observed_at'])
        if not start<=final_time<=game_time<=observed or observed!=max(primary_time,game_time):
            return False
        activity = explicit['offensive_activity'];seen=set()
        if not isinstance(activity,list) or not 1<=len(activity)<=2:
            return False
        for item in activity:
            category=item['category'];count=item['count'];yards=item['yards']
            if (category not in ('rushing','receiving') or category in seen
                    or type(count) is not int or not 0<count<=10000
                    or type(yards) is not int or abs(yards)>10000):
                return False
            seen.add(category)
            if row[category+'_yards'] is not None and row[category+'_yards']!=yards:
                return False
            if category=='receiving' and count!=row['receptions']:
                return False
        return True
    except (KeyError,TypeError,ValueError,ArithmeticError):
        return False
