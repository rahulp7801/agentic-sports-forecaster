"""Current roster presentation metadata, separate from immutable forecasts."""
import argparse
import asyncio
import json
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sportsbet.db.connection import create_async_pool
from sportsbet.dashboard import publish_snapshot
from sportsbet.prop.availability import fetch_event_availability, player_availability
from sportsbet.prop.cross_venue import _evidence, _game, _digest, _name, _sha256, _timestamp
from sportsbet.model_contract import PROP_MARKETS
from sportsbet.schedules import SPORTS

MAX_EVENTS, MAX_PLAYERS, MAX_EVENT_PLAYERS = 20, 200, 50
MAX_PUBLIC_BYTES = 16 * 1024 * 1024
PUBLIC_IDENTITIES_QUERY = '''SELECT snapshot_key,payload FROM dashboard_snapshots
WHERE snapshot_key=ANY($1::text[]) AND octet_length(payload::text)<=16777216'''

SIGNAL_IDENTITIES_QUERY = '''WITH latest AS MATERIALIZED (
    SELECT payload FROM dashboard_snapshots
    WHERE snapshot_key LIKE $1 AND updated_at > NOW() - INTERVAL '14 days'
    ORDER BY updated_at DESC LIMIT 6
), bounded AS MATERIALIZED (
    SELECT payload->'signals' AS signals FROM latest
    WHERE jsonb_typeof(payload->'signals')='array'
      AND jsonb_array_length(payload->'signals')<=500
)
SELECT DISTINCT signal->>'player' AS player,signal->>'game_id' AS game_id,
    signal->>'home_team' AS home_team,signal->>'away_team' AS away_team
FROM bounded CROSS JOIN LATERAL jsonb_array_elements(signals) AS signal
WHERE jsonb_typeof(signal)='object'
  AND signal->>'player' IS NOT NULL AND signal->>'game_id' IS NOT NULL
  AND signal->>'home_team' IS NOT NULL AND signal->>'away_team' IS NOT NULL
ORDER BY game_id,player LIMIT 1000'''


def profile(context, player, player_id, now, *, sport='nfl', expected_team=None):
    evidence, _ = player_availability(context, player, now, player_id=player_id,sport=sport)
    if (evidence['status'] != 'observed' or not evidence.get('player_id')
            or not evidence.get('player_image_url')):
        return None
    if expected_team is not None:
        abbreviation,name = expected_team
        matches=[team for team in context.get('teams',[]) if team.get('abbreviation')==abbreviation]
        canonical=lambda value:'LA Clippers' if sport=='nba' and value=='Los Angeles Clippers' else value
        if (evidence['team']!=abbreviation or len(matches)!=1
                or canonical(matches[0].get('name'))!=canonical(name)):
            return None
    return dict(player=player, name=evidence.get('roster_player_name', player),
        team=evidence['team'], player_id=evidence['player_id'],
        image_url=evidence['player_image_url'], captured_at=evidence['captured_at'],
        source_url=evidence['roster_source_url'], source_sha256=evidence['roster_source_sha256'],
        **{key:evidence[key] for key in ('jersey','position') if evidence.get(key)},
        **{key:evidence[key] for key in ('identity_source_url','identity_source_sha256') if key in evidence})


def _bounded_public(value):
    """Bound untrusted containers before hashing or walking public identity evidence."""
    pending=[(value,0)]; nodes=characters=0
    while pending:
        item,depth=pending.pop();nodes+=1
        if nodes>600000 or depth>14:
            raise ValueError('Public identity evidence exceeds bounds')
        if type(item) is dict:
            if len(item)>5000 or any(type(key) is not str or len(key)>200 for key in item):
                raise ValueError('Invalid public identity object')
            pending.extend((entry,depth+1) for entry in item.values())
            characters+=sum(len(key) for key in item)
        elif type(item) is list:
            if len(item)>5000: raise ValueError('Public identity list exceeds bounds')
            pending.extend((entry,depth+1) for entry in item)
        elif type(item) is str:
            if len(item)>10000: raise ValueError('Public identity string exceeds bounds')
            characters+=len(item)
        elif item is not None and type(item) not in (bool,int,float):
            raise ValueError('Invalid public identity scalar')
        elif type(item) is float and not math.isfinite(item):
            raise ValueError('Invalid public identity number')
        if characters>MAX_PUBLIC_BYTES: raise ValueError('Public identity evidence exceeds bounds')


def _public_payload(value):
    # asyncpg returns JSONB as text unless the connection installs a custom codec.
    if isinstance(value,str):
        if len(value)>MAX_PUBLIC_BYTES or len(value.encode('utf-8'))>MAX_PUBLIC_BYTES:
            raise ValueError('Public identity evidence exceeds bounds')
        def object_pairs(pairs):
            result={}
            for key,item in pairs:
                if key in result: raise ValueError('Duplicate public identity field')
                result[key]=item
            return result
        def invalid_constant(_): raise ValueError('Invalid public identity number')
        value=json.loads(value,object_pairs_hook=object_pairs,parse_constant=invalid_constant)
    _bounded_public(value)
    return value


def _uuid(value):
    if not isinstance(value,str) or str(UUID(value))!=value:
        raise ValueError('Invalid public target identity')
    return value


def _label(value):
    if (not isinstance(value,str) or not 0<len(value)<=100 or value!=value.strip()
            or any(ord(character)<32 or ord(character)==127 for character in value)):
        raise ValueError('Invalid profile identity label')
    return value


def public_profile_identities(handoff, slate, sport, now):
    """Read identities only from exact, fresh, committed public handoff/slate joins."""
    if sport not in ('nfl','nba'): raise ValueError('Unsupported profile sport')
    _bounded_public(handoff);_bounded_public(slate)
    evidence,captured,version = _evidence(handoff,sport,now)
    if (not isinstance(slate,dict) or slate.get('sport')!=sport
            or slate.get('status') not in ('complete','partial')
            or type(slate.get('games')) is not list or len(slate['games'])>100):
        raise ValueError('Invalid profile schedule')
    slate_at=_timestamp(slate.get('captured_at'))
    if not -1 <= (now-slate_at).total_seconds() <= 900:
        raise ValueError('Profile schedule is stale or future')
    sources=slate.get('sources')
    prefix='https://site.api.espn.com/apis/site/v2/sports/'+SPORTS[sport]+'/scoreboard?dates='
    if (type(sources) is not list or not 0<len(sources)<=8
            or any(not isinstance(url,str) or not re.fullmatch(re.escape(prefix)+r'[0-9]{8}&limit=1000',url) for url in sources)):
        raise ValueError('Invalid profile schedule source')
    if len(evidence['games'])>100 or len(evidence['player_targets'])>1000:
        raise ValueError('Public profile identity count exceeds bounds')
    targets=evidence['player_targets']
    for target_id,target in targets.items():
        _uuid(target_id);_uuid(target['team_target_id']);_label(target['player_name'])
        if (not _sha256(target.get('target_sha256')) or not _sha256(target.get('target_page_sha256'))
                or not _timestamp(target['target_request_started_at'])<=_timestamp(target['target_received_at'])<=captured):
            raise ValueError('Invalid public target receipt')
    for game in evidence['games']:
        for key in ('milestone_id','home_team_id','away_team_id'): _uuid(game[key])
        for key in ('home_team_aliases','away_team_aliases'):
            if type(game[key]) is not list or not 0<len(game[key])<=8: raise ValueError('Invalid team aliases')
            for name in game[key]: _label(name)
    games={};seen_ids=set();seen_matches=set()
    for game in slate['games']:
        event_id=game['provider_event_id'];home=_label(game['home_name']);away=_label(game['away_name'])
        start=_timestamp(game['game_time'])
        if (not isinstance(event_id,str) or not re.fullmatch(r'[1-9][0-9]{0,19}',event_id) or event_id in seen_ids
                or type(game.get('completed')) is not bool or _name(home)==_name(away)):
            raise ValueError('Ambiguous profile event')
        seen_ids.add(event_id)
        for key in ('home_abbr','away_abbr'):
            if not isinstance(game.get(key),str) or not re.fullmatch('[A-Z]{2,3}',game[key]):
                raise ValueError('Invalid profile team abbreviation')
        if game['home_abbr']==game['away_abbr']: raise ValueError('Ambiguous profile teams')
        if game['completed'] or not now<start<=now+timedelta(days=7): continue
        event=dict(id=event_id,home_team=home,away_team=away,commence_time=game['game_time'])
        matched=_game(event,evidence)
        if matched is None: continue
        if matched['milestone_id'] in seen_matches: raise ValueError('Ambiguous profile event join')
        seen_matches.add(matched['milestone_id']);games[matched['milestone_id']]=(game,matched,event)
    names_by_game={milestone:Counter(_name(item['player_name']) for item in targets.values()
        if item['team_target_id'] in (matched['home_team_id'],matched['away_team_id']))
        for milestone,(_,matched,_) in games.items()}
    result={};tickers=set();slate_sha=_digest(slate)
    for quote in evidence['quotes']:
        _uuid(quote['milestone_id']);player_id=_uuid(quote['player_target_id']);team_id=_uuid(quote['team_target_id'])
        ticker=quote.get('ticker')
        if not isinstance(ticker,str) or not ticker or ticker in tickers: raise ValueError('Ambiguous public prop')
        tickers.add(ticker)
        if quote['milestone_id'] not in games: continue
        game,matched,event=games[quote['milestone_id']];start=_timestamp(event['commence_time'])
        target=targets.get(player_id)
        if (not isinstance(target,dict) or target['team_target_id']!=team_id
                or team_id not in (matched['home_team_id'],matched['away_team_id'])
                or _timestamp(quote['scheduled_game_start_time'])!=start
                or quote.get('strike_type')!='greater' or quote.get('prop_type') not in PROP_MARKETS[sport].values()
                or quote.get('execution_ready') is not False or quote.get('settlement_equivalent') is not False
                or (version==2 and any(not isinstance(quote.get(key),str) or not quote[key]
                                      for key in ('event_ticker','series_ticker')))
                or not all(_sha256(quote.get(key)) for key in ('market_sha256','source_page_sha256','rules_sha256'))):
            raise ValueError('Invalid public prop identity receipt')
        received,requested=map(_timestamp,(quote['received_at'],quote['request_started_at']))
        if not requested<=received<=captured or received>=start or not -1<=(now-received).total_seconds()<=300:
            raise ValueError('Invalid public prop chronology')
        if names_by_game[quote['milestone_id']][_name(target['player_name'])]!=1: continue
        side='home' if team_id==matched['home_team_id'] else 'away'
        provenance=dict(snapshot_key='kalshi-props:'+sport,captured_at=handoff['captured_at'],
            evidence_sha256=handoff['evidence_sha256'],slate_captured_at=slate['captured_at'],slate_payload_sha256=slate_sha,
            game_id=event['id'],game_start_time=event['commence_time'],player_target_id=player_id,team_target_id=team_id,
            target_sha256=target['target_sha256'],target_page_sha256=target['target_page_sha256'],
            target_request_started_at=target['target_request_started_at'],target_received_at=target['target_received_at'],
            market_sha256=quote['market_sha256'],source_page_sha256=quote['source_page_sha256'],
            quote_request_started_at=quote['request_started_at'],quote_received_at=quote['received_at'])
        result.setdefault((event['id'],player_id),dict(player=target['player_name'],game_id=event['id'],
            home_team=event['home_team'],away_team=event['away_team'],
            expected_team=(game[side+'_abbr'],game[side+'_name']),identity_context=provenance))
    return list(result.values())


def bounded_profile_events(rows):
    """Bound both sources together before any roster/crosswalk request."""
    events={};seen_events=set();players=set()
    for row in rows:
        try:
            player=_label(row['player']);home=_label(row['home_team']);away=_label(row['away_team'])
            game_id=_label(row['game_id']);name=_name(player)
            if _name(home)==_name(away): continue
            event_id=(game_id,_name(home),_name(away))
            key=event_id
            if event_id not in seen_events and len(seen_events)>=MAX_EVENTS: continue
            if name not in players and len(players)>=MAX_PLAYERS: continue
            event=events.get(key)
            if event is not None and name not in event['players'] and len(event['players'])>=MAX_EVENT_PLAYERS: continue
            seen_events.add(event_id);players.add(name)
            event=events.setdefault(key,dict(event=dict(id=game_id,home_team=home,away_team=away),players={}))
            event['players'].setdefault(name,row)
        except (KeyError,TypeError,ValueError,AttributeError): continue
    return list(events.values())


async def run(sports, *, expected_public_captures=None):
    pool = await create_async_pool()
    results = {}
    try:
        for sport in sports:
            async with pool.acquire() as conn:
                rows = await conn.fetch(SIGNAL_IDENTITIES_QUERY, f'signals:{sport}:%')
                snapshots = await conn.fetch(PUBLIC_IDENTITIES_QUERY,['kalshi-props:'+sport,'slate:'+sport])
                public=[];public_status='rejected'
                try:
                    inputs={row['snapshot_key']:row['payload'] for row in snapshots}
                    expected={'kalshi-props:'+sport,'slate:'+sport}
                    if len(inputs)!=len(snapshots) or not inputs.keys()<=expected:
                        raise ValueError('Invalid profile snapshots')
                    if inputs.keys()!=expected:
                        public_status='missing'
                    else:
                        handoff=_public_payload(inputs['kalshi-props:'+sport])
                        slate=_public_payload(inputs['slate:'+sport])
                        if expected_public_captures is not None:
                            pins=expected_public_captures[sport]
                            if (set(pins)!={'market_captured_at','slate_captured_at'}
                                    or not isinstance(pins['market_captured_at'],str)
                                    or not isinstance(pins['slate_captured_at'],str)
                                    or handoff['captured_at']!=pins['market_captured_at']
                                    or slate['captured_at']!=pins['slate_captured_at']):
                                raise ValueError('Public profile capture changed')
                        public=public_profile_identities(handoff,slate,sport,datetime.now(timezone.utc))
                        public_status='observed'
                except (KeyError,TypeError,ValueError,AttributeError,RecursionError): pass
                events=bounded_profile_events([*public,*rows])
                player_ids = {}
                if sport == 'nfl' and events:
                    names=sorted({row['player'].lower() for event in events for row in event['players'].values()})
                    ids=await conn.fetch('SELECT lower(player_name) AS player_name,'
                        'array_agg(DISTINCT player_id::text) AS player_ids FROM player_stats '
                        'WHERE lower(player_name)=ANY($1::text[]) GROUP BY lower(player_name)',names)
                    player_ids={row['player_name']:row['player_ids'] for row in ids}
            profiles = {}
            failures = 0
            for group in events:
                players={row['player'] for row in group['players'].values()}
                context = await fetch_event_availability(group['event'],sport,player_names=players)
                for row in group['players'].values():
                    player=row['player']
                    player_id = None
                    if sport=='nfl':
                        matches=player_ids.get(player.lower(),[])
                        if len(matches)==1: player_id=matches[0]
                    value=profile(context,player,player_id,datetime.now(timezone.utc),sport=sport,
                                  expected_team=row.get('expected_team'))
                    if value and row.get('identity_context'): value['identity_context']=row['identity_context']
                    if value: profiles.setdefault(player,value)
                    else: failures+=1
            # Empty inputs and provider failures must retain the last capture and its timestamps.
            if profiles:
                publish_snapshot('player-profiles:'+sport,dict(sport=sport,
                    captured_at=datetime.now(timezone.utc).isoformat(),profiles=list(profiles.values())))
            results[sport]=dict(profiles=len(profiles),unavailable=failures,
                signal_identities=len(rows),public_identities=len(public),public_input_status=public_status,
                selected_events=len(events),selected_players=sum(len(event['players']) for event in events))
        return results
    finally:
        await pool.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sport',choices=['nfl','nba','both'],default='both')
    args=parser.parse_args()
    try:
        print(json.dumps(asyncio.run(run(['nfl','nba'] if args.sport=='both' else [args.sport]))))
    except Exception as exc:
        raise SystemExit(f'Player metadata update unavailable ({type(exc).__name__})') from None


if __name__=='__main__': main()
