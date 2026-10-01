from copy import deepcopy
from datetime import datetime,timedelta,date,timezone
import base64,gzip,json
from unittest.mock import AsyncMock,MagicMock,patch
import pytest
from sportsbet.quant import nfl_recent_role_shadow as role
from sportsbet.ingestion.provenance import stat_row_sha256,row_sha256
from sportsbet.scan import quotes_from_event
from sportsbet.quant.market_baseline import paired_market_baseline
from sportsbet.ledger import Ledger


def fixture(player_id='00-0030506', team='KC'):
    now=datetime.fromisoformat(role.FROZEN_AT)+timedelta(seconds=30)
    player=deepcopy(role.artifact()[1][player_id]);observed=(now-timedelta(seconds=2)).isoformat()
    data=dict(observed_at=(now-timedelta(seconds=1)).isoformat(),observed_before=observed,
        cutoff='2026-09-30',season_floor=2024,players=[player],stats=[],snaps=[],supplements=[])
    for season,weeks in ((2024,15),(2025,15),(2026,3)):
        for week in range(1,weeks+1):
            day=date(season,9,13)+timedelta(days=7*(week-1))
            game_id=f'{season}_{week:02}_JAX_{team}'
            common=dict(game_id=game_id,game_date=day.isoformat(),home_team=team,away_team='JAX')
            stat=dict(player_id=player_id,season=season,week=week,team=team,
                passing_yards=None,rushing_yards=None,receptions=3 if season<2026 else 0,
                receiving_yards=120 if season<2026 else 0)
            snap=dict(game_id=game_id,season=season,week=week,player_name=player['player'],pfr_player_id=player['pfr_player_id'],
                position='TE',team=team,opponent='JAX',offense_snaps=40,defense_snaps=0)
            data['stats'].append(common|dict(stat=stat|dict(source_provider='nflverse',source_sha256='a'*64,
                source_record_sha256=stat_row_sha256('nfl',stat),source_observed_at=observed)))
            data['snaps'].append(common|dict(snap=snap|dict(source_provider='nflverse',source_sha256='b'*64,
                source_record_sha256=row_sha256(snap),source_observed_at=observed)))
    event=dict(id='recent-role-test',home_team='Home',away_team='Away',commence_time='2026-09-30T20:00:00Z',
        bookmakers=[dict(key='book',markets=[dict(key='player_receptions',last_update=observed,
            outcomes=[dict(name=side,point=.5,price=-110,description=player['player']) for side in ('Over','Under')])])])
    quotes=quotes_from_event(event,'nfl');quote=quotes[0]
    payload=dict(player=player['player'],player_id=player_id,sport='nfl',game_id=event['id'],
        home_team=event['home_team'],away_team=event['away_team'],game_date=data['cutoff'],forecast_cutoff=data['cutoff'],
        game_start_time=event['commence_time'],prop_type='receptions',line=.5,direction='over',
        sportsbook=quote.sportsbook,american_odds=quote.price,quote_time=observed,
        quote_source_provider=quote.source_provider,quote_source_sha256=quote.source_sha256,
        quote_source_record_sha256=quote.source_record_sha256,captured_at=now.isoformat(),model_generated_at=now.isoformat(),
        model_version=role.BASELINE_VERSION,history_policy_version=role.HISTORY_POLICY,history_observed_before=observed,
        model_sample_size=33,model_probability=30.5/34,model_mean_stat=round(90/33,2),push_probability=0,
        accepted=False,stake_fraction=0,gate_reason='research_fixture',**paired_market_baseline(quote,quotes),
        availability=dict(status='observed',roster_confirmed=True,player_id=player['espn_player_id'],team=team,
            captured_at=now.isoformat(),roster_source_url='https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/12/roster',
            roster_source_sha256='c'*64))
    return payload,data


def test_broader_candidate_reweights_recent_role_and_replays_exact_inputs():
    from sportsbet.quant.nfl_role_shadow import artifact as old_artifact
    p,data=fixture();before=deepcopy((p,data))
    assert p['player_id'] not in old_artifact()[1]
    result=role.shadow_record(p,data);assert result['status']=='predicted',result
    assert (p,data)==before
    assert result['counts']['current_role_games']==3 and result['counts']['older_games']==30
    assert result['probability']==pytest.approx(20*(30.5/31)/23)
    assert result['probability']<p['model_probability']
    assert result['inputs']['encoding']=='gzip-base64-json-v1'
    assert len(json.dumps(result['inputs']))<16000
    assert role.verified_shadow_probability(p|{'role_history_shadow':result})==result['probability']
    changed=deepcopy(result);changed['counts']['current_role_games']=4
    assert role.verified_shadow_probability(p|{'role_history_shadow':changed}) is None


@pytest.mark.parametrize('fault',['missing_stat','missing_snap','late_source','late_input','changed_cutoff',
    'wrong_baseline','nan_mean','wrong_model','wrong_policy','roster_id','roster_team','roster_stale','integer_line'])
def test_incomplete_or_noncausal_inputs_abstain(fault):
    p,data=fixture()
    if fault=='missing_stat':data['stats'].pop()
    if fault=='missing_snap':data['snaps'].pop()
    if fault=='late_source':data['stats'][0]['stat']['source_observed_at']=p['captured_at']
    if fault=='late_input':data['observed_at']=(datetime.fromisoformat(p['captured_at'])+timedelta(seconds=1)).isoformat()
    if fault=='changed_cutoff':data['observed_before']=p['captured_at']
    if fault=='wrong_baseline':p['model_probability']=.7
    if fault=='nan_mean':p['model_mean_stat']=float('nan')
    if fault=='wrong_model':p['model_version']='empirical-jeffreys-v4'
    if fault=='wrong_policy':p['history_policy_version']='other'
    if fault=='roster_id':p['availability']['player_id']='999'
    if fault=='roster_team':p['availability']['team']='DEN'
    if fault=='roster_stale':p['availability']['captured_at']='2026-09-28T00:00:00Z'
    if fault=='integer_line':p['line']=1
    assert role.shadow_record(p,data)['status']=='unavailable'


def test_gzip_payload_is_bounded_committed_and_has_no_trailing_member():
    p,data=fixture();result=role.shadow_record(p,data);encoded=result['inputs']
    for update in (dict(sha256='0'*64),dict(uncompressed_bytes=role.MAX_INPUT_BYTES+1),
                   dict(data=encoded['data']+'!!!'),dict(data=base64.b64encode(base64.b64decode(encoded['data'])+gzip.compress(b'{}')).decode())):
        changed=deepcopy(result);changed['inputs'].update(update)
        assert role.verified_shadow_probability(p|{'role_history_shadow':changed}) is None
    raw=b' '* (role.MAX_INPUT_BYTES+1)
    bomb=dict(encoding='gzip-base64-json-v1',sha256='0'*64,uncompressed_bytes=role.MAX_INPUT_BYTES,
        data=base64.b64encode(gzip.compress(raw)).decode())
    with pytest.raises(ValueError):role.decoded_inputs(json.dumps(bomb))


def test_archived_zero_requires_both_receipt_and_insertion_before_capture():
    from sportsbet.quant.nfl_history_supplements import plan_supplements
    from tests.test_nfl_final_evidence import bundle,NOW
    from tests.test_nfl_history_supplements import game
    p,data=fixture('00-0036422','DEN')
    item=plan_supplements(json.dumps(bundle()),[],[game()],now=NOW)['updates'][0]
    item['inserted_at']=data['observed_before']
    data['stats']=[r for r in data['stats'] if (r['stat']['season'],r['stat']['week'])!=(2026,2)]
    data['supplements']=[dict(supplement=item,game_date='2026-09-20',home_team='DEN',away_team='JAX')]
    result=role.shadow_record(p,data);assert result['status']=='predicted',result
    assert result['recovered_games']==1
    item['inserted_at']=p['captured_at']
    assert role.shadow_record(p,data)['status']=='unavailable'


def test_late_server_receipt_is_owned_idempotent_and_cannot_rewrite_primary(tmp_path):
    p,data=fixture();p['role_history_shadow']=role.shadow_record(p,data)
    ledger=Ledger(tmp_path/'late.sqlite',database_url='')
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime.fromisoformat(p['captured_at'])+timedelta(minutes=6)
    with patch('sportsbet.ledger.datetime',Clock):key=ledger.record('same',p)
    row=ledger.predictions()[0]
    assert row['role_history_shadow']['reason']=='invalid_or_late_recording'
    assert role.verified_recorded_shadow_probability(row) is None
    assert ledger.record('same',p)==key
    assert row['model_probability']==p['model_probability'] and row['accepted'] is False
    changed=deepcopy(p);changed['role_history_shadow']['probability']=.5
    with pytest.raises(ValueError,match='immutable'):ledger.record('same',changed)


def test_valid_ledger_receipt_and_earliest_attempt_audit(tmp_path):
    from sportsbet.quant.nfl_recent_role_audit import report_role_history_shadow
    p,data=fixture();p['role_history_shadow']=role.shadow_record(p,data)
    ledger=Ledger(tmp_path/'valid.sqlite',database_url='')
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime.fromisoformat(p['captured_at'])+timedelta(seconds=1)
    with patch('sportsbet.ledger.datetime',Clock):ledger.record('same',p)
    row=ledger.predictions()[0]
    assert role.verified_recorded_shadow_probability(row)==p['role_history_shadow']['probability']
    result=report_role_history_shadow([row],'nfl')
    assert result['markets']['receptions']['counts']['valid_predictions']==1
    assert result['markets']['receptions']['status']=='insufficient_data' and result['promote'] is False
    earlier=deepcopy(row);earlier['prediction_id']='earlier';earlier['captured_at']=data['observed_at']
    earlier['model_generated_at']=earlier['captured_at']
    earlier['role_history_shadow']={'model_version':role.VERSION,'status':'unavailable','reason':'incomplete_participation_history'}
    result=report_role_history_shadow([earlier,row],'nfl')
    assert result['earliest_attempts']==1
    assert result['markets']['receptions']['counts']['valid_predictions']==0
    assert result['markets']['receptions']['unavailable_reasons']=={'incomplete_participation_history':1}


@pytest.mark.asyncio
async def test_loader_is_bounded_readonly_and_retains_source_cutoff():
    p,data=fixture();conn=MagicMock();conn.fetch=AsyncMock(side_effect=[data['stats'],data['snaps'],[]])
    pool=MagicMock();pool.acquire.return_value.__aenter__=AsyncMock(return_value=conn)
    conn.transaction.return_value.__aenter__=AsyncMock()
    cutoff=datetime.fromisoformat(data['observed_before'])
    result=await role.load_inputs(pool,'nfl',2026,date(2026,9,30),{p['player_id']},observed_before=cutoff)
    conn.transaction.assert_called_once_with(isolation='repeatable_read',readonly=True)
    assert all(call.args[-2]==cutoff and call.args[-1]==81 for call in conn.fetch.call_args_list)
    assert result[p['player_id']]['observed_before']==cutoff.isoformat()
    assert len(result[p['player_id']]['stats'])==33


@pytest.mark.asyncio
@pytest.mark.parametrize('failed_read',[False,True])
async def test_scanner_candidate_preserves_public_forecasts_and_exposure(tmp_path,monkeypatch,failed_read):
    from decimal import Decimal
    from sportsbet import scan
    from sportsbet.config import settings
    from sportsbet.graph.models import PropResult
    p,data=fixture();now=datetime.fromisoformat(p['captured_at'])
    data['observed_at']=data['observed_before']=p['captured_at']
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return now
    monkeypatch.setattr(scan,'datetime',Clock);monkeypatch.setattr('sportsbet.ledger.datetime',Clock)
    event=dict(id=p['game_id'],home_team=p['home_team'],away_team=p['away_team'],commence_time=p['game_start_time'],
        bookmakers=[dict(key='book',markets=[dict(key='player_receptions',last_update=p['quote_time'],
            outcomes=[dict(name=side,point=.5,price=-110,description=p['player']) for side in ('Over','Under')])])])
    conn=MagicMock();conn.fetch=AsyncMock(return_value=[dict(normalized_name=p['player'].lower(),player_id=p['player_id'])])
    pool=MagicMock();pool.acquire.return_value.__aenter__=AsyncMock(return_value=conn)
    monkeypatch.setattr(scan,'write_player_prop_snapshots',AsyncMock())
    graph=MagicMock();graph.ainvoke=AsyncMock(return_value={'prop_result':PropResult(true_probability=Decimal(str(p['model_probability'])),
        sample_size=33,mean_stat=Decimal('2.73'),confidence_interval=(Decimal('.80'),Decimal('.95')))})
    monkeypatch.setattr(scan,'create_graph',lambda **kwargs:graph)
    monkeypatch.setattr(scan,'player_availability',lambda *args,**kwargs:(p['availability']|{'subject_status':'available','teammates':[]},None))
    monkeypatch.setattr(scan,'screened_availability_reports',lambda *args:[])
    monkeypatch.setattr(scan,'historical_availability_splits',AsyncMock(return_value=[]))
    monkeypatch.setattr(scan,'load_ngs_evidence',AsyncMock(return_value=None))
    monkeypatch.setattr(settings,'history_shadow_enabled',False)
    loader=AsyncMock(side_effect=RuntimeError('private failure')) if failed_read else AsyncMock(return_value={p['player_id']:data})
    monkeypatch.setattr(role,'load_inputs',loader)
    baseline=Ledger(tmp_path/'baseline.sqlite',database_url='');candidate=Ledger(tmp_path/'candidate.sqlite',database_url='')
    monkeypatch.setattr(settings,'role_history_shadow_enabled',False)
    before=await scan.evaluate_event(pool,event,'nfl',baseline,'same')
    loader.assert_not_awaited()
    monkeypatch.setattr(settings,'role_history_shadow_enabled',True)
    after=await scan.evaluate_event(pool,event,'nfl',candidate,'same')
    assert before['signals']==after['signals'] and before['coverage']['counts']==after['coverage']['counts']
    assert loader.call_args.kwargs['observed_before']==now
    assert len(candidate.predictions())==2
    for row in candidate.predictions():
        if failed_read:assert row['role_history_shadow']['reason']=='history_read_failed'
        else:assert role.verified_recorded_shadow_probability(row) is not None,row['role_history_shadow']
        assert row['accepted'] is False and row['stake_fraction']==0
    assert all('role_history_shadow' not in s for s in after['signals'])
    with candidate.connect() as db:assert db.execute('SELECT count(*) FROM exposure').fetchone()[0]==0

@pytest.mark.parametrize('portrait',[False,True])
def test_verified_roster_identity_reaches_recent_role_without_requiring_photo(portrait):
    from sportsbet.prop.availability import player_availability,NFL_PLAYER_IDS_URL
    p,data=fixture();binding=data['players'][0];espn=binding['espn_player_id'];name=binding['player'];now=datetime.fromisoformat(p['captured_at'])
    team=dict(name='Home',abbreviation='KC',roster_names=[name],roster_ids={espn:name},roster_statuses={name:'Active'},reports=[],
        roster_source_url=p['availability']['roster_source_url'],roster_source_sha256=p['availability']['roster_source_sha256'])
    if portrait:team['portraits']={name:dict(player_id=espn,player_image_url=f'https://a.espncdn.com/i/headshots/nfl/players/full/{espn}.png')}
    context=dict(status='observed',captured_at=p['captured_at'],source_url='https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries',
        source_sha256='a'*64,teams=[team],player_identities={p['player_id']:espn},
        identity_source=dict(url=NFL_PLAYER_IDS_URL,source_sha256='b'*64,retrieved_at=p['captured_at']))
    evidence,reason=player_availability(context,name,now,player_id=p['player_id'],sport='nfl')
    assert reason is None and evidence.get('player_id')==espn
    assert ('player_image_url' in evidence)==portrait
    p['availability']=evidence
    result=role.shadow_record(p,data)
    assert result['status']=='predicted',result
    assert p['model_probability']==30.5/34 and evidence['probability_adjusted'] is False
