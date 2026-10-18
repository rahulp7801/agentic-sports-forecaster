from datetime import datetime, timedelta, timezone
from copy import deepcopy
from sportsbet.player_profiles import profile
from sportsbet.player_profiles import run, PUBLIC_IDENTITIES_QUERY
import pytest


def context():
    now=datetime.now(timezone.utc)
    return now,dict(status='observed',captured_at=now.isoformat(),source_url='injuries',source_sha256='a'*64,teams=[dict(abbreviation='BUF',
        roster_names=['Player'],roster_ids={'123':'Player'},roster_statuses={'Player':'Active'},
        reports=[dict(player='Teammate',status='Out',position='WR',reported_at=now.isoformat())],
        injury_coverage='observed',injury_source_url='injuries',injury_source_sha256='a'*64,
        roster_source_url='roster',roster_source_sha256='b'*64,
        portraits={'Player':dict(player_id='123',player_image_url='portrait',jersey='0',position='QB')})])


def test_profile_is_presentation_only_even_when_teammates_gate_forecast():
    now,data=context(); before=deepcopy(data)
    result=profile(data,'Player',None,now)
    assert result['jersey']=='0' and result['position']=='QB'
    assert result['source_sha256']=='b'*64 and result['name']=='Player'
    assert not {'true_prob','gated','subject_status','teammates'} & result.keys()
    assert data==before
    assert profile(data,'Other',None,now) is None
    assert profile(data,'Player',None,now+timedelta(hours=2)) is None


def test_alias_requires_captured_crosswalk_and_uses_canonical_roster_profile():
    now,data=context()
    data.update(player_identities={'00-0037248':'123'},identity_source=dict(
        url='https://github.com/nflverse/nflverse-data/releases/download/players/players.csv',
        source_sha256='c'*64,retrieved_at=now.isoformat()))
    result=profile(data,'Book Name','00-0037248',now)
    assert result['player']=='Book Name' and result['name']=='Player'
    assert result['identity_source_sha256']=='c'*64
    assert profile(data,'Book Name','00-0000000',now) is None


@pytest.mark.asyncio
async def test_scheduled_profile_refresh_uses_recorded_slate_without_new_quotes(monkeypatch):
    now,data=context(); publications=[]; events=[]
    class Connection:
        async def fetch(self,sql,*args):
            if sql==PUBLIC_IDENTITIES_QUERY:
                assert args==(['kalshi-props:nfl','slate:nfl'],)
                return []
            if 'dashboard_snapshots' in sql:
                assert args==('signals:nfl:%',)
                assert "jsonb_array_elements" in sql and "payload->'signals'" in sql
                return [dict(player='Player',game_id='game',home_team='Home',away_team='Away')]
            assert args==(['player'],)
            return [dict(player_name='player',player_ids=['00-0037248'])]
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
    class Pool:
        closed=False
        def acquire(self): return Connection()
        async def close(self): self.closed=True
    pool=Pool()
    async def create_pool(): return pool
    async def collect(event,sport,**kwargs):
        events.append(event);assert sport=='nfl' and kwargs['player_names']=={'Player'}
        return data
    monkeypatch.setattr('sportsbet.player_profiles.create_async_pool',create_pool)
    monkeypatch.setattr('sportsbet.player_profiles.fetch_event_availability',collect)
    monkeypatch.setattr('sportsbet.player_profiles.publish_snapshot',lambda *args:publications.append(args))
    expected=dict(signal_identities=1,public_identities=0,public_input_status='missing',selected_events=1,selected_players=1)
    assert (await run(['nfl']))['nfl']==dict(profiles=1,unavailable=0,**expected)
    assert events==[dict(id='game',home_team='Home',away_team='Away')]
    assert publications[0][0]=='player-profiles:nfl'
    assert publications[0][1]['profiles'][0]['jersey']=='0' and pool.closed
    publications.clear();data['status']='unavailable'
    assert (await run(['nfl']))['nfl']==dict(profiles=0,unavailable=1,**expected)
    assert publications==[]  # Provider failure cannot overwrite the last capture.


@pytest.mark.asyncio
@pytest.mark.parametrize('sport', ['nfl', 'nba'])
async def test_empty_recent_identities_preserve_original_profile_capture(monkeypatch, sport):
    stamp='2026-10-01T12:00:00+00:00'
    key='player-profiles:'+sport
    stored={key:dict(sport=sport,captured_at=stamp,profiles=[dict(
        player='Archive Player',player_id='123',team='BUF',captured_at=stamp,
        image_url='https://a.espncdn.com/i/headshots/'+sport+'/players/full/123.png',
        source_url='https://site.api.espn.com/apis/site/v2/sports/roster',
        source_sha256='a'*64)])}
    original=deepcopy(stored); publications=[]
    class Connection:
        async def fetch(self,sql,*args):
            if sql==PUBLIC_IDENTITIES_QUERY:
                assert args==(['kalshi-props:'+sport,'slate:'+sport],)
                return []
            assert 'dashboard_snapshots' in sql and args==('signals:'+sport+':%',)
            return []
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
    class Pool:
        closed=False
        def acquire(self): return Connection()
        async def close(self): self.closed=True
    pool=Pool()
    async def create_pool(): return pool
    async def unexpected_collection(*args,**kwargs):
        pytest.fail('Empty identity inputs must not collect new provider evidence')
    def publish(snapshot_key,payload):
        publications.append(snapshot_key)
        stored[snapshot_key]=payload
    monkeypatch.setattr('sportsbet.player_profiles.create_async_pool',create_pool)
    monkeypatch.setattr('sportsbet.player_profiles.fetch_event_availability',unexpected_collection)
    monkeypatch.setattr('sportsbet.player_profiles.publish_snapshot',publish)
    assert await run([sport])=={sport:dict(profiles=0,unavailable=0,signal_identities=0,
        public_identities=0,public_input_status='missing',selected_events=0,selected_players=0)}
    assert publications==[] and stored==original and pool.closed


@pytest.mark.asyncio
@pytest.mark.parametrize('fault,category', [
    ('snapshot_set', ('snapshots', 'invalid_set')),
    ('decode', ('snapshots', 'decode')),
    ('pins', ('capture_pins', 'shape')),
    ('pin_mismatch', ('capture_pins', 'mismatch')),
    ('handoff', ('handoff', 'shape')),
])
async def test_rejected_public_inputs_report_only_fixed_categories_without_collection(monkeypatch, fault, category):
    import json
    import sportsbet.player_profiles as profiles
    captured=datetime.now(timezone.utc).isoformat()
    handoff=dict(captured_at=captured)
    slate=dict(captured_at=captured)
    rows=[dict(snapshot_key='kalshi-props:nba',payload=json.dumps(handoff)),
        dict(snapshot_key='slate:nba',payload=json.dumps(slate))]
    pins=dict(market_captured_at=captured,slate_captured_at=captured)
    if fault=='snapshot_set': rows.append(dict(rows[0]))
    if fault=='decode': rows[0]['payload']='PRIVATE_PLAYER https://private.example/secret'
    if fault=='pins': pins.pop('market_captured_at')
    if fault=='pin_mismatch': pins['market_captured_at']='different-private-capture'
    if fault=='handoff':
        def invalid_handoff(*args):
            raise ValueError('PRIVATE_PLAYER https://private.example/secret')
        monkeypatch.setattr(profiles,'_evidence',invalid_handoff)
    class Connection:
        async def fetch(self,sql,*args):
            if sql==profiles.PUBLIC_IDENTITIES_QUERY: return rows
            assert sql==profiles.SIGNAL_IDENTITIES_QUERY
            return []
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
    class Pool:
        closed=False
        def acquire(self): return Connection()
        async def close(self): self.closed=True
    pool=Pool()
    async def create_pool(): return pool
    async def forbidden(*args,**kwargs): pytest.fail('Rejected identity inputs must not collect rosters')
    def forbidden_publication(*args): pytest.fail('Rejected empty inputs must retain the previous capture')
    monkeypatch.setattr(profiles,'create_async_pool',create_pool)
    monkeypatch.setattr(profiles,'fetch_event_availability',forbidden)
    monkeypatch.setattr(profiles,'publish_snapshot',forbidden_publication)
    original=deepcopy(rows)
    result=(await profiles.run(['nba'],expected_public_captures={'nba':pins}))['nba']
    assert result==dict(profiles=0,unavailable=0,signal_identities=0,public_identities=0,
        public_input_status='rejected',selected_events=0,selected_players=0,
        rejection_stage=category[0],rejection_reason=category[1])
    assert rows==original and pool.closed
    assert 'PRIVATE_' not in json.dumps(result) and 'https://' not in json.dumps(result)


@pytest.mark.parametrize('portraits',[{}, {'Player': {'jersey': '0'}}, {'Player': {'player_id': '123', 'player_image_url': 'wrong'}}])
def test_verified_roster_without_valid_photo_does_not_crash_profile_refresh(portraits):
    now,data=context()
    data['sport']='nfl'
    data['teams'][0]['roster_source_url']='https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/2/roster'
    data['teams'][0]['portraits']=portraits
    assert profile(data,'Player',None,now) is None
