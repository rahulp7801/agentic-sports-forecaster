"""Collect and publish bounded ESPN schedules, preserving source failures."""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import httpx

from sportsbet.diagnostics import failure_stage

SPORTS = {'nba':'basketball/nba', 'nfl':'football/nfl', 'cfb':'football/college-football'}
STAT_TEAM_ALIASES = {'nba':{}, 'nfl':{'LAR':'LA', 'WSH':'WAS'}, 'cfb':{}}
NBA_ADDITIONAL_STAT_IDENTITIES = {
    'GS': ('Golden State Warriors', 'GSW'),
    'NO': ('New Orleans Pelicans', 'NOP'),
    'NY': ('New York Knicks', 'NYK'),
    'SA': ('San Antonio Spurs', 'SAS'),
    'WSH': ('Washington Wizards', 'WAS'),
}


def scheduled_stat_teams(sport: str, game: dict, *, identity_version: int = 2) -> frozenset[str]:
    """Translate exact ESPN abbreviations to the stat provider's identities."""
    if type(identity_version) is int and identity_version == 4:
        if sport != 'nba':
            raise ValueError('Unsupported schedule identity version')
        projected={};additional=False
        for side in ('home','away'):
            value=game.get(side+'_abbr')
            identity=NBA_ADDITIONAL_STAT_IDENTITIES.get(value) if isinstance(value,str) else None
            if identity is not None:
                name,canonical=identity
                if game.get(side+'_name')!=name:
                    raise ValueError('Invalid NBA schedule identity')
                value=canonical;additional=True
            elif value=='UTAH':
                if game.get(side+'_name')!='Utah Jazz':
                    raise ValueError('Invalid Utah schedule identity')
                value='UTA'
            projected[side+'_abbr']=value
        if not additional:
            raise ValueError('Additional NBA schedule identity is required')
        # Canonical comparisons are opt-in; the raw schedule and old proofs stay unchanged.
        return scheduled_stat_teams(sport,projected)
    if type(identity_version) is int and identity_version == 3:
        if sport != 'nba':
            raise ValueError('Unsupported schedule identity version')
        projected={};utah=False
        for side in ('home','away'):
            value=game.get(side+'_abbr')
            if value=='UTAH':
                if game.get(side+'_name')!='Utah Jazz':
                    raise ValueError('Invalid Utah schedule identity')
                value='UTA';utah=True
            projected[side+'_abbr']=value
        if not utah:
            raise ValueError('Utah schedule identity is required')
        # Preserve raw source fields and the version2 interpretation of old proofs.
        return scheduled_stat_teams(sport,projected)
    if identity_version != 2:
        raise ValueError('Unsupported schedule identity version')
    if sport not in STAT_TEAM_ALIASES:
        raise ValueError('Unsupported sport')
    values=[]
    for field in ('home_abbr','away_abbr'):
        value=game.get(field)
        pattern='[A-Z0-9-]{2,8}' if sport=='cfb' else '[A-Z]{2,3}'
        if not isinstance(value,str) or not re.fullmatch(pattern,value):
            raise ValueError('Invalid schedule team identity')
        values.append(STAT_TEAM_ALIASES[sport].get(value,value))
    if len(set(values))!=2:
        raise ValueError('Schedule teams must be distinct')
    return frozenset(values)


def parse_day(data: dict, day: str, label: str) -> list[dict]:
    if not isinstance(data.get('events'),list):
        raise ValueError('Missing schedule events')
    games=[]
    for event in data['events']:
        start=datetime.fromisoformat(event['date'].replace('Z','+00:00'))
        if start.utcoffset() is None:
            raise ValueError('Schedule start must include a timezone')
        if start.astimezone(ZoneInfo('America/New_York')).strftime('%Y%m%d')!=day:
            continue  # NFL responses can contain other games from the same week.
        competition,=event['competitions']
        completed=event.get('status',{}).get('type',{}).get('completed')
        if type(completed) is not bool:
            raise ValueError('Schedule completion state is missing')
        home,=[c['team'] for c in competition['competitors'] if c['homeAway']=='home']
        away,=[c['team'] for c in competition['competitors'] if c['homeAway']=='away']
        if not event['id'] or any(not t.get(k) for t in (home,away) for k in ('abbreviation','displayName')):
            raise ValueError('Incomplete schedule identity')
        games.append(dict(provider_event_id=str(event['id']),home_abbr=home['abbreviation'],
            away_abbr=away['abbreviation'],home_name=home['displayName'],away_name=away['displayName'],
            date=day,label=label,game_time=start.isoformat(),completed=completed))
    if len({g['provider_event_id'] for g in games})!=len(games):
        raise ValueError('Duplicate schedule event')
    return games


async def collect(sport: str, now: datetime | None = None, *, offsets: tuple[int, ...] = (-1,0,1)) -> dict:
    if sport not in SPORTS:
        raise ValueError('Unsupported sport')
    if (not offsets or len(set(offsets))!=len(offsets)
            or any(type(offset) is not int or not -30 <= offset <= 6 for offset in offsets)):
        raise ValueError('Schedule offsets must be unique integer days from -30 through 6')
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Schedule time requires a timezone')
    today=now.astimezone(ZoneInfo('America/New_York')).date()
    games=[];failures=[];sources=[]
    labels={-1:'Yesterday',0:'Today',1:'Tomorrow'}
    async with httpx.AsyncClient(timeout=10,follow_redirects=False) as client:
        for offset in offsets:
            day=(today+timedelta(days=offset)).strftime('%Y%m%d')
            label=labels.get(offset,(today+timedelta(days=offset)).isoformat())
            url=f'https://site.api.espn.com/apis/site/v2/sports/{SPORTS[sport]}/scoreboard?dates={day}&limit=1000'
            try:
                response=await client.get(url)
                response.raise_for_status()
                games.extend(parse_day(response.json(),day,label))
                sources.append(url)
            except Exception as exc:
                failures.append(dict(date=day,error_type=type(exc).__name__))
    return dict(sport=sport,captured_at=datetime.now(timezone.utc).isoformat(),as_of_date=str(today),
        status='complete' if not failures else 'unavailable' if len(failures)==len(offsets) else 'partial',
        games=games,partial=bool(failures),failures=failures,sources=sources)


async def publish_slate(sport: str, now: datetime | None = None, *,
                        receipt: dict[str,str] | None = None) -> str:
    """Publish current/upcoming games and optionally retain original capture metadata."""
    with failure_stage('slate_publication','arguments'):
        if sport not in SPORTS:
            raise ValueError('Unsupported sport')
    with failure_stage('slate_publication','initialize'):
        if receipt is not None:
            receipt.clear()
        from sportsbet.dashboard import load_snapshot, publish_snapshot
        now=now or datetime.now(timezone.utc)
        today=str(now.astimezone(ZoneInfo('America/New_York')).date())
    with failure_stage('slate_publication','cache_read'):
        previous=load_snapshot('slate:'+sport) or {}
        try:
            age=now-datetime.fromisoformat(previous['captured_at'].replace('Z','+00:00'))
            if (previous.get('as_of_date')==today and previous.get('status') in ('complete','partial')
                    and timedelta(0)<=age<=timedelta(minutes=10)):
                if receipt is not None:
                    receipt['captured_at']=previous['captured_at']
                return 'cached'
        except (KeyError,ValueError,TypeError,AttributeError):
            pass
    with failure_stage('slate_publication','collection'):
        slate=await collect(sport,now,offsets=tuple(range(7)))
    with failure_stage('slate_publication','projection'):
        games=sorted((game for game in slate.get('games',[]) if game.get('completed') is False),
            key=lambda game:(datetime.fromisoformat(game['game_time']),game['provider_event_id']))
        truncated=len(games)>100
        status=slate['status']
        if status=='complete' and truncated:
            status='partial'
        bounded={**slate,'games':games[:100],'partial':status=='partial','status':status}
    if status in ('complete','partial'):
        with failure_stage('slate_publication','publication'):
            captured=bounded['captured_at']
            publish_snapshot('slate:'+sport,bounded)
            if receipt is not None:
                receipt['captured_at']=captured
    return status


def _write_slate_receipt(path: str, sport: str, receipt: dict[str,str]) -> None:
    captured=receipt.get('captured_at')
    if set(receipt)!={'captured_at'} or not isinstance(captured,str):
        raise ValueError('Invalid schedule publication receipt')
    parsed=datetime.fromisoformat(captured.replace('Z','+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Schedule receipt lacks timezone')
    destination=Path(path)
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_name(destination.name+'.tmp')
    temporary.write_text(json.dumps({'slates':{sport:{'captured_at':captured}}},
                                   separators=(',',':'))+'\n',encoding='utf-8')
    temporary.replace(destination)


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sport',choices=sorted(SPORTS),required=True)
    parser.add_argument('--report-output',help='Write the original slate publication receipt to this file')
    args=parser.parse_args()
    try:
        receipt={}
        # The CLI aggregate phase follows any more precise internal failure.
        with failure_stage('slate_publication','publish'):
            status=asyncio.run(publish_slate(args.sport,receipt=receipt)
                               if args.report_output else publish_slate(args.sport))
        with failure_stage('slate_publication','status'):
            if status not in ('complete','partial','cached','unavailable'):
                raise ValueError('Invalid schedule publication status')
        if status=='unavailable':
            with failure_stage('slate_publication','output'):
                print(status)
            raise SystemExit(2)
        if args.report_output:
            with failure_stage('slate_publication','receipt_write'):
                _write_slate_receipt(args.report_output,args.sport,receipt)
        with failure_stage('slate_publication','output'):
            print(status)
    except Exception as exc:
        raise SystemExit(f'Schedule publication unavailable ({type(exc).__name__})') from None


if __name__=='__main__':
    main()
