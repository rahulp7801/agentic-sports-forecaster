"""Validate archived explicit CFB receiving totals; never infer zero from omission."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from zoneinfo import ZoneInfo

from sportsbet.ingestion.provenance import stat_row_sha256
from sportsbet.ledger import utc_timestamp, verified_settlement_evidence, VERIFIED_SETTLEMENT_SOURCE
from sportsbet.schedules import scheduled_stat_teams
from sportsbet.settlement import _candidate

SUMMARY = 'https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event='
GAMELOG = 'https://site.web.api.espn.com/apis/common/v3/sports/football/college-football/athletes/{player}/gamelog?season={season}'


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def integer(value, *, nonnegative=False):
    if type(value) is not str or not re.fullmatch(r'-?[0-9]{1,5}', value):
        raise ValueError('Explicit integer stat required')
    result=int(value)
    if abs(result)>10000 or (nonnegative and result<0):
        raise ValueError('Invalid explicit statistic')
    return result


def inspect_bundle(bundle: dict, *, now=None) -> list[dict]:
    now=now or datetime.now(timezone.utc)
    if bundle.get('version')!=1 or not 1<=len(bundle['players'])<=50 or not 1<=len(bundle['sources'])<=100:
        raise ValueError('Invalid recovery bundle bounds')
    sources={};size=0
    for source in bundle['sources']:
        raw=source['response_text'];length=len(raw.encode('utf-8'));size+=length
        if (not 0<length<=4_000_000 or size>20_000_000 or source['url'] in sources
                or digest(raw)!=source['sha256'] or utc_timestamp(source['observed_at'])>now):
            raise ValueError('Invalid source commitment')
        sources[source['url']]=source
    def read(url):
        receipt=sources[url]
        return json.loads(receipt['response_text']),receipt
    results=[];seen=set()
    for player in bundle['players']:
        identity=player['player_id'];event=player['espn_event_id']
        if (any(not isinstance(v,str) or not re.fullmatch('[1-9][0-9]{0,14}',v) for v in (identity,event))
                or (identity,event) in seen):
            raise ValueError('Invalid or duplicate player/game identity')
        seen.add((identity,event))
        summary,final=read(SUMMARY+event)
        h=summary['header'];comp,=h['competitions']
        if (h['id']!=event or comp['id']!=event or h['league']['slug']!='college-football'
                or h['season']['type']!=2 or comp['status']['type']['completed'] is not True
                or comp['status']['type']['name']!='STATUS_FINAL'):
            raise ValueError('Completed CFB regular-season game required')
        season=h['season']['year'];week=h['week'];start=utc_timestamp(comp['date'])
        day=start.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        final_time=utc_timestamp(final['observed_at'])
        if (type(season) is not int or season!=(start.year if start.month>=8 else start.year-1)
                or type(week) is not int or not 1<=week<=25 or day!=player['date']
                or not start<=final_time<=now):
            raise ValueError('Invalid final chronology')
        home,=[t for t in comp['competitors'] if t['homeAway']=='home']
        away,=[t for t in comp['competitors'] if t['homeAway']=='away']
        if len(comp['competitors'])!=2 or home['id']==away['id']:
            raise ValueError('Invalid game competitors')
        for team in (home,away):
            if (not re.fullmatch('[1-9][0-9]{0,14}',team['id']) or team['team']['id']!=team['id']
                    or any(not isinstance(team['team'].get(k),str) or not team['team'][k].strip()
                        or len(team['team'][k])>limit for k,limit in [('displayName',100),('abbreviation',10)])):
                raise ValueError('Invalid team identity')
        game=dict(provider_event_id=event,date=day,game_time=start.isoformat(),completed=True,
            home_name=home['team']['displayName'],away_name=away['team']['displayName'],
            home_abbr=home['team']['abbreviation'],away_abbr=away['team']['abbreviation'])
        scheduled_stat_teams('cfb',game)
        data,receipt=read(GAMELOG.format(player=identity,season=season))
        observed=utc_timestamp(receipt['observed_at'])
        if not final_time<=observed<=now:
            raise ValueError('Game log predates observed final status')
        for key,value in [('season',str(season)),('league','college-football')]:
            f,=[f for f in data['filters'] if f['name']==key]
            if f['value']!=value:raise ValueError('Wrong game-log scope')
        result=dict(player_id=identity,game=game,status='unavailable',reason='explicit_game_stats_missing')
        entries=[e for s in data['seasonTypes'] for c in s['categories'] if c['type']=='event'
                 for e in c.get('events', ()) if e['eventId']==event]
        if not entries:
            results.append(result);continue
        entry,=entries
        if any(e['eventId']==event and c.get('splitType')!='2'
                for s in data['seasonTypes'] for c in s['categories'] if c['type']=='event' for e in c.get('events', ())):
            raise ValueError('Wrong game-log season type')
        names=data['names']
        if (any(type(c['count']) is not int or not 0<=c['count']<=100 for c in data['categories'])
                or len(names)!=len(set(names)) or len(names)!=len(entry['stats'])
                or sum(c['count'] for c in data['categories'])!=len(names)):
            raise ValueError('Ambiguous game-log statistic columns')
        values=dict(zip(names,entry['stats'],strict=True))
        if not {'receptions','receivingYards'}<=values.keys():
            results.append(result);continue
        meta=data['events'][event]
        if (meta['id']!=event or utc_timestamp(meta['gameDate'])!=start or meta['week']!=week
                or meta['homeTeamId']!=home['id'] or meta['awayTeamId']!=away['id']
                or meta['homeTeamScore']!=home['score'] or meta['awayTeamScore']!=away['score']):
            raise ValueError('Game-log event does not match final summary')
        team,=[t for t in (home,away) if t['id']==meta['team']['id']]
        opponent=away if team is home else home
        if meta['opponent']['id']!=opponent['id']:
            raise ValueError('Wrong opponent identity')
        receptions=integer(values['receptions'],nonnegative=True)
        yards=integer(values['receivingYards'])
        if receptions==0 and yards!=0:raise ValueError('Inconsistent receiving totals')
        # Explicit game-log zero requires independent observed offensive activity
        # in the final box score, never roster membership or category omission.
        boxes=summary['boxscore']['players']
        box,=[b for b in boxes if b['team']['id']==team['id']]
        if len(boxes)!=2 or {b['team']['id'] for b in boxes}!={home['id'],away['id']}:
            raise ValueError('Ambiguous box-score teams')
        if any(a['athlete']['id']==identity for b in boxes if b is not box
                for c in b['statistics'] for a in c['athletes']):
            raise ValueError('Athlete occurs on both teams')
        activity=[];athlete=None
        for category,count_label,count_name,yards_name in [
                ('rushing','CAR','rushingAttempts','rushingYards'),
                ('receiving','REC','receptions','receivingYards')]:
            categories=[c for c in box['statistics'] if c['name']==category]
            if len(categories)>1:raise ValueError('Duplicate box-score category')
            if not categories:continue
            cat=categories[0];matches=[a for a in cat['athletes'] if a['athlete']['id']==identity]
            if len(matches)>1:raise ValueError('Duplicate athlete in box-score category')
            if not matches:continue
            a=matches[0];labels=cat['labels']
            if len(labels)!=len(set(labels)) or len(labels)!=len(a['stats']):
                raise ValueError('Ambiguous box-score statistics')
            stats=dict(zip(labels,a['stats'],strict=True))
            count=integer(stats[count_label],nonnegative=True);box_yards=integer(stats['YDS'])
            if count!=integer(values[count_name],nonnegative=True) or box_yards!=integer(values[yards_name]):
                raise ValueError('Final sources disagree')
            if count>0:
                if athlete and athlete['displayName']!=a['athlete']['displayName']:
                    raise ValueError('Conflicting athlete identity')
                athlete=a['athlete'];activity.append(dict(category=category,count=count,yards=box_yards))
        if not activity:
            result['reason']='offensive_participation_unconfirmed';results.append(result);continue
        if not isinstance(athlete.get('displayName'),str) or not 0<len(athlete['displayName'].strip())<=100:
            raise ValueError('Invalid athlete name')
        row=dict(game_id=int(event),athlete_id=int(identity),player_name=athlete['displayName'],
            team_id=int(team['id']),passing_yards=None,rushing_yards=None,
            receiving_yards=yards,receptions=receptions,season=season,week=week,
            game_date=start.date().isoformat(),is_home=team is home,
            team_name=team['team']['displayName'],team_abbreviation=team['team']['abbreviation'],
            opponent_id=int(opponent['id']),opponent_name=opponent['team']['displayName'],
            opponent_abbreviation=opponent['team']['abbreviation'])
        commitments=[{k:r[k] for k in ('url','sha256','observed_at')} for r in (final,receipt)]
        source=dict(version=1,kind='cfb_explicit_receiving_game_log',athlete_id=identity,
            event_id=event,offensive_activity=activity,sources=commitments)
        result.update(status='verified_explicit_stats',stat_row=row,observed_at=observed.isoformat(),
            stat_record_sha256=stat_row_sha256('cfb',row),source_evidence=source,
            source_sha256=digest(json.dumps(source,sort_keys=True,separators=(',',':'))))
        result.pop('reason');results.append(result)
    return results


def plan_recovery(rows: list[dict], evidence: list[dict]) -> dict:
    updates=[];pending=[]
    for p in rows:
        if p.get('outcome') is not None or p.get('sport')!='cfb' or p.get('prop_type') not in ('receptions','rec_yds'):
            continue
        matches=[]
        for item in evidence:
            if item['player_id']!=p.get('player_id'):continue
            try:
                candidate=_candidate(p,'cfb',[item['game']])
            except (KeyError,TypeError,ValueError,ArithmeticError):
                continue
            if candidate and utc_timestamp(p['game_start_time'])==utc_timestamp(item['game']['game_time']):
                matches.append((item,candidate))
        if len(matches)!=1:continue
        item,(game,day,line)=matches[0]
        if item['status']!='verified_explicit_stats':
            pending.append(p['prediction_id']);continue
        actual=item['stat_row']['receptions' if p['prop_type']=='receptions' else 'receiving_yards']
        outcome='push' if actual==line else ((actual>line)==(p['direction']=='over'))
        proof=dict(schedule_identity_version=2,**{k:game[k] for k in ('provider_event_id','date','home_abbr','away_abbr','home_name','away_name','completed','game_time')},
            player_id=p['player_id'],prop_type=p['prop_type'],actual_value=str(actual),stat_provider='espn',
            stat_source_sha256=item['source_sha256'],stat_record_sha256=item['stat_record_sha256'],
            stat_observed_at=item['observed_at'],stat_row=item['stat_row'],explicit_final_source=item['source_evidence'])
        ref=f"espn_schedule+espn:{game['provider_event_id']}:sha256:{digest(json.dumps(proof,sort_keys=True,separators=(',',':')))}"
        if not verified_settlement_evidence(p,outcome,VERIFIED_SETTLEMENT_SOURCE,ref,item['observed_at'],actual,proof):
            raise ValueError('Recovery failed settlement proof contract')
        updates.append(dict(prediction_id=p['prediction_id'],outcome=outcome,actual=actual,source_ref=ref,
            observed_at=item['observed_at'],evidence=proof,payload=p))
    return dict(updates=updates,unresolved=pending)
