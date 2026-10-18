"""Synthetic public identity receipts; no provider or database operations."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from uuid import UUID

import pytest
import sportsbet.player_profiles as profiles
from sportsbet.prop.cross_venue import _digest


NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


def uid(number):
    return str(UUID(int=number))


def receipts(sport='nfl', *, now=NOW, count=1):
    captured=(now-timedelta(seconds=10)).isoformat()
    requested=(now-timedelta(seconds=12)).isoformat()
    received=(now-timedelta(seconds=11)).isoformat()
    start=(now+timedelta(hours=2)).isoformat()
    home,away=('Buffalo Bills','New York Jets') if sport=='nfl' else ('Los Angeles Clippers','Boston Celtics')
    habbr,aabbr=('BUF','NYJ') if sport=='nfl' else ('LAC','BOS')
    game=dict(milestone_id=uid(1),scheduled_game_start_time=start,main_game_event_ticker='GAME-EXAMPLE',
        home_team_id=uid(2),away_team_id=uid(3),home_team_aliases=[home],away_team_aliases=[away])
    target=dict(player_name='Player',team_target_id=uid(2),target_sha256='a'*64,target_page_sha256='b'*64,
        target_request_started_at=requested,target_received_at=received)
    quote=dict(ticker='PROP-EXAMPLE-0',event_ticker='PROP-EXAMPLE',series_ticker='PROP',milestone_id=uid(1),
        scheduled_game_start_time=start,market_occurrence_time=start,
        prop_type='pass_yds' if sport=='nfl' else 'points',player_target_id=uid(4),team_target_id=uid(2),
        strike_type='greater',line='100.5',yes_ask=dict(cost='0.51',displayed_size='100.00'),
        no_ask=dict(cost='0.52',displayed_size='100.00'),request_started_at=requested,received_at=received,
        market_sha256='c'*64,source_page_sha256='d'*64,rules_sha256='e'*64,
        settlement_profile='unclassified_v1',execution_ready=False,settlement_equivalent=False)
    evidence=dict(games=[game],player_targets={uid(4):target},quotes=[dict(quote,ticker='PROP-EXAMPLE-'+str(i)) for i in range(count)],
        fee_contexts={},partial_coverage=False,coverage=dict(discovery_complete=True,series_observed=1,series_expected=1,
            structured_quote_markets=count,player_resolved_quote_markets=count,fee_contexts_observed=0,fee_contexts_expected=0))
    handoff=dict(schema_version=2,sport=sport,status='observed',execution_ready=False,captured_at=captured,
        evidence=evidence,evidence_sha256=_digest(evidence))
    dates=[(now+timedelta(days=offset)).strftime('%Y%m%d') for offset in range(-1,7)]
    path='football/nfl' if sport=='nfl' else 'basketball/nba'
    slate=dict(sport=sport,status='complete',captured_at=captured,games=[dict(provider_event_id='12345',
        home_name=home,away_name=away,home_abbr=habbr,away_abbr=aabbr,game_time=start,completed=False)],
        sources=['https://site.api.espn.com/apis/site/v2/sports/'+path+'/scoreboard?dates='+date+'&limit=1000' for date in dates])
    return handoff,slate


def rehash(handoff):
    handoff['evidence_sha256']=_digest(handoff['evidence'])


@pytest.mark.parametrize('sport',['nfl','nba'])
def test_exact_public_identity_join_preserves_original_receipts_and_eight_source_daily_slate(sport):
    handoff,slate=receipts(sport);before=deepcopy((handoff,slate))
    rows=profiles.public_profile_identities(handoff,slate,sport,NOW)
    assert len(rows)==1 and rows[0]['game_id']=='12345' and rows[0]['player']=='Player'
    assert rows[0]['expected_team']==('BUF','Buffalo Bills') if sport=='nfl' else rows[0]['expected_team']==('LAC','Los Angeles Clippers')
    receipt=rows[0]['identity_context']
    assert receipt['captured_at']==handoff['captured_at'] and receipt['slate_captured_at']==slate['captured_at']
    assert receipt['evidence_sha256']==handoff['evidence_sha256'] and receipt['slate_payload_sha256']==_digest(slate)
    assert receipt['player_target_id']==uid(4) and (handoff,slate)==before
    assert not {'true_prob','qualified','recommendation','price'} & rows[0].keys()


@pytest.mark.parametrize('change',[
    'hash','sport','stale_handoff','future_handoff','stale_slate','future_slate','source','uuid',
    'target_hash','target_clock','target_team','quote_team','quote_start','quote_hash','quote_clock','quote_series',
    'duplicate_slate_id','duplicate_game','partial','degraded',
])
def test_invalid_public_identity_receipts_fail_closed(change):
    handoff,slate=receipts();e=handoff['evidence'];q=e['quotes'][0];t=e['player_targets'][uid(4)]
    if change=='hash': handoff['evidence_sha256']='f'*64
    elif change=='sport': handoff['sport']='nba'
    elif change=='stale_handoff': handoff['captured_at']=(NOW-timedelta(seconds=301)).isoformat()
    elif change=='future_handoff': handoff['captured_at']=(NOW+timedelta(seconds=2)).isoformat()
    elif change=='stale_slate': slate['captured_at']=(NOW-timedelta(seconds=901)).isoformat()
    elif change=='future_slate': slate['captured_at']=(NOW+timedelta(seconds=2)).isoformat()
    elif change=='source': slate['sources']=['https://untrusted.invalid/scoreboard']
    elif change=='uuid': q['player_target_id']='123'
    elif change=='target_hash': t['target_sha256']='not-a-hash'
    elif change=='target_clock': t['target_request_started_at']=NOW.isoformat()
    elif change=='target_team': t['team_target_id']=uid(3)
    elif change=='quote_team': q['team_target_id']=uid(9)
    elif change=='quote_start': q['scheduled_game_start_time']=(NOW+timedelta(hours=3)).isoformat()
    elif change=='quote_hash': q['source_page_sha256']='invalid'
    elif change=='quote_clock': q['request_started_at']=NOW.isoformat()
    elif change=='quote_series': q['series_ticker']=None
    elif change=='duplicate_slate_id': slate['games'].append(deepcopy(slate['games'][0]))
    elif change=='duplicate_game': e['games'].append(deepcopy(e['games'][0]))
    elif change=='partial': e['partial_coverage']=True
    elif change=='degraded': handoff['status']='degraded'
    if change!='hash': rehash(handoff)
    with pytest.raises(ValueError): profiles.public_profile_identities(handoff,slate,'nfl',NOW)


@pytest.mark.parametrize('change',['ordered_teams','start','completed','started'])
def test_nonmatching_or_past_slate_cannot_seed_profiles(change):
    handoff,slate=receipts();game=slate['games'][0]
    if change=='ordered_teams': game['home_name'],game['away_name']=game['away_name'],game['home_name']
    elif change=='start': game['game_time']=(NOW+timedelta(hours=3)).isoformat()
    elif change=='completed': game['completed']=True
    else: game['game_time']=NOW.isoformat()
    assert profiles.public_profile_identities(handoff,slate,'nfl',NOW)==[]


def test_ambiguous_same_name_targets_are_not_resolved_by_first_match():
    handoff,slate=receipts();e=handoff['evidence']
    e['player_targets'][uid(5)]=dict(e['player_targets'][uid(4)],team_target_id=uid(3));rehash(handoff)
    assert profiles.public_profile_identities(handoff,slate,'nfl',NOW)==[]


def test_public_decoder_handles_real_jsonb_strings_and_current_scale_without_unbounded_input():
    handoff,slate=receipts(count=2932)
    wire=json.dumps(handoff)
    assert len(wire)>2_000_000  # Production-shaped compact fields, no raw market or rules text.
    assert len(profiles.public_profile_identities(profiles._public_payload(wire),slate,'nfl',NOW))==1
    for wire in ('{"x":1,"x":2}','{"x":NaN}','not-json','x'*(profiles.MAX_PUBLIC_BYTES+1)):
        with pytest.raises(ValueError): profiles._public_payload(wire)
    with pytest.raises(ValueError): profiles._public_payload({'quotes':[None]*5001})


def seed(player='Player',game='12345',home='Home',away='Away'):
    return dict(player=player,game_id=game,home_team=home,away_team=away)


def test_merged_inputs_are_deduplicated_and_bounded_before_roster_fetch():
    row=seed();assert len(profiles.bounded_profile_events([row,deepcopy(row)]))==1
    # Team pairs alone do not erase distinct recorded game IDs.
    groups=profiles.bounded_profile_events([row,dict(row,game_id='12346')])
    assert len(groups)==2
    rows=[seed(str(i),str(i),'Home '+str(i),'Away '+str(i)) for i in range(25)]
    assert len(profiles.bounded_profile_events(rows))==20
    assert len(profiles.bounded_profile_events([seed(str(i)) for i in range(100)])[0]['players'])==50
    rows=[seed('Player '+str(j*50+i),str(j),'Home '+str(j),'Away '+str(j)) for j in range(5) for i in range(50)]
    assert sum(len(event['players']) for event in profiles.bounded_profile_events(rows))==200


def roster(sport, *, now, team='home'):
    home,away=('Buffalo Bills','New York Jets') if sport=='nfl' else ('LA Clippers','Boston Celtics')
    habbr,aabbr=('BUF','NYJ') if sport=='nfl' else ('LAC','BOS')
    path='football/nfl' if sport=='nfl' else 'basketball/nba'
    teams=[]
    for side,name,abbr,identifier in [('home',home,habbr,'2'),('away',away,aabbr,'3')]:
        teams.append(dict(name=name,abbreviation=abbr,roster_names=['Player'] if side==team else [],
            roster_ids={'123':'Player'} if side==team else {},roster_statuses={'Player':'Active'},reports=[],
            injury_coverage='observed',injury_source_url='injuries',injury_source_sha256='a'*64,
            roster_source_url='https://site.api.espn.com/apis/site/v2/sports/'+path+'/teams/'+identifier+'/roster',
            roster_source_sha256='b'*64,portraits={'Player':dict(player_id='123',
                player_image_url='https://a.espncdn.com/i/headshots/'+sport+'/players/full/123.png')}))
    return dict(sport=sport,status='observed',captured_at=now.isoformat(),source_url='injuries',source_sha256='a'*64,teams=teams)


@pytest.mark.parametrize('sport',['nfl','nba'])
def test_profile_keeps_captured_team_side_after_roster_resolution_and_passes_sport(sport):
    handoff,slate=receipts(sport);row=profiles.public_profile_identities(handoff,slate,sport,NOW)[0]
    result=profiles.profile(roster(sport,now=NOW),row['player'],None,NOW,sport=sport,expected_team=row['expected_team'])
    assert result['player_id']=='123' and result['team']==row['expected_team'][0]
    assert profiles.profile(roster(sport,now=NOW,team='away'),row['player'],None,NOW,
        sport=sport,expected_team=row['expected_team']) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('sport',['nfl','nba'])
@pytest.mark.parametrize('public_mode',['valid','invalid','changed_market','changed_slate','unknown_market'])
async def test_refresh_uses_jsonb_handoff_without_signals_and_retains_signal_fallback(monkeypatch,sport,public_mode):
    now=datetime.now(timezone.utc);handoff,slate=receipts(sport,now=now)
    if public_mode=='invalid': handoff['evidence_sha256']='f'*64
    pins=dict(market_captured_at=handoff['captured_at'],slate_captured_at=slate['captured_at'])
    if public_mode=='changed_market': pins['market_captured_at']=now.isoformat()
    if public_mode=='changed_slate': pins['slate_captured_at']=now.isoformat()
    if public_mode=='unknown_market': pins['market_captured_at']=None
    calls=[];published=[];ids=[]
    signals=[] if public_mode=='valid' else [seed(home=slate['games'][0]['home_name'],away=slate['games'][0]['away_name'])]
    class Connection:
        async def fetch(self,sql,*args):
            if sql==profiles.SIGNAL_IDENTITIES_QUERY: return signals
            if sql==profiles.PUBLIC_IDENTITIES_QUERY:
                assert args==(['kalshi-props:'+sport,'slate:'+sport],)
                return [dict(snapshot_key='kalshi-props:'+sport,payload=json.dumps(handoff)),
                    dict(snapshot_key='slate:'+sport,payload=json.dumps(slate))]
            assert sport=='nfl' and args==(['player'],)
            return []  # No history ID: the Kalshi UUID must never become an athlete ID.
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
    class Pool:
        closed=False
        def acquire(self): return Connection()
        async def close(self): self.closed=True
    pool=Pool()
    async def create_pool(): return pool
    async def fetch(event,requested_sport,**kwargs):
        calls.append((event,requested_sport,kwargs));return roster(sport,now=datetime.now(timezone.utc))
    original=profiles.profile
    def checked_profile(context,player,player_id,now,**kwargs):
        ids.append(player_id);return original(context,player,player_id,now,**kwargs)
    monkeypatch.setattr(profiles,'create_async_pool',create_pool)
    monkeypatch.setattr(profiles,'fetch_event_availability',fetch)
    monkeypatch.setattr(profiles,'profile',checked_profile)
    monkeypatch.setattr(profiles,'publish_snapshot',lambda *args:published.append(args))
    result=(await profiles.run([sport],expected_public_captures={sport:pins}))[sport]
    assert result==dict(profiles=1,unavailable=0,signal_identities=len(signals),
        public_identities=1 if public_mode=='valid' else 0,public_input_status='observed' if public_mode=='valid' else 'rejected',
        selected_events=1,selected_players=1)
    assert len(calls)==1 and calls[0][1]==sport and calls[0][2]=={'player_names':{'Player'}}
    assert ids==[None] and pool.closed and len(published)==1
    row=published[0][1]['profiles'][0]
    assert row['player_id']=='123'
    if public_mode=='valid':
        assert row['identity_context']['captured_at']==handoff['captured_at']
        assert row['identity_context']['slate_captured_at']==slate['captured_at']
        assert datetime.fromisoformat(row['captured_at'])>datetime.fromisoformat(row['identity_context']['captured_at'])
    else: assert 'identity_context' not in row


@pytest.mark.asyncio
async def test_reused_six_minute_market_does_not_recollect_or_refresh_stale_public_identities(monkeypatch):
    from unittest.mock import AsyncMock
    from sportsbet import daily
    now=datetime.now(timezone.utc)
    handoff,slate=receipts(now=now-timedelta(minutes=6))
    slate['captured_at']=now.isoformat()
    stored={'kalshi-props:nfl':handoff}
    cached=dict(schema_version=2,sport='nfl',captured_at=handoff['captured_at'],execution_ready=False,
        evidence_sha256='a'*64,comparisons=[],sources={
            'sportsbook':dict(status='not_requested',partial_coverage=True),
            'kalshi':dict(status='observed',partial_coverage=False),
            'prizepicks':dict(status='observed',partial_coverage=False)})
    class Connection:
        async def fetch(self,sql,*args):
            if sql==profiles.SIGNAL_IDENTITIES_QUERY: return []
            assert sql==profiles.PUBLIC_IDENTITIES_QUERY
            return [dict(snapshot_key=key,payload=json.dumps(stored[key])) for key in args[0]]
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
    class Pool:
        def acquire(self): return Connection()
        async def close(self): pass
    async def create_pool(): return Pool()
    class Audit:
        def report(self,*args,**kwargs): return {}
        def predictions(self): return []
    async def collect(sport,clock,**kwargs):
        offsets=kwargs.get('offsets')
        value=deepcopy(slate)
        if offsets==(2,3,4,5,6): value['sources']=slate['sources'][3:]
        else:
            value['games']=[]
            value['sources']=slate['sources'][:3] if offsets is None else []
        return value
    watch=AsyncMock(side_effect=AssertionError('Cached quotes must not be recollected'))
    roster_fetch=AsyncMock(side_effect=AssertionError('Stale public identities must not fetch rosters'))
    publication=AsyncMock()
    monkeypatch.setattr(profiles,'create_async_pool',create_pool)
    monkeypatch.setattr(profiles,'fetch_event_availability',roster_fetch)
    monkeypatch.setattr(profiles,'publish_snapshot',publication)
    monkeypatch.setattr(daily,'refresh_profiles',profiles.run)
    monkeypatch.setattr(daily,'watch',watch)
    monkeypatch.setattr(daily,'load_snapshot',lambda key:cached if key=='markets:nfl' else None)
    monkeypatch.setattr(daily,'collect_schedule',collect)
    monkeypatch.setattr(daily,'publish_snapshot',lambda key,value:stored.update({key:deepcopy(value)}))
    monkeypatch.setattr(daily,'refresh_history',lambda *args:dict(status='complete'))
    monkeypatch.setattr(daily,'Ledger',Audit)
    monkeypatch.setattr(daily,'settle_final_props',lambda *args:dict(status='complete'))
    result=await daily.run(['nfl'],'public_daily',20)
    assert result['markets']['nfl']['captured_at']==handoff['captured_at']
    assert result['markets']['nfl']['research_pair_status']=='market_reused'
    assert result['profiles']['nfl']==dict(status='degraded',profiles=0,unavailable=0,signal_identities=0,
        public_identities=0,public_input_status='rejected',selected_events=0,selected_players=0)
    assert result['status']=='degraded'
    watch.assert_not_called();roster_fetch.assert_not_called();publication.assert_not_called()
