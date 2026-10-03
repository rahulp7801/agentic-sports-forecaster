"""Consumer NFL cohorts replay commitments without changing model probabilities."""
from copy import deepcopy
from datetime import date, datetime, timezone

import pytest

from sportsbet.ingestion.provenance import row_sha256, stat_row_sha256
from sportsbet.prop.nfl_participation_evidence import nfl_participation_split

NOW=datetime(2026,9,29,tzinfo=timezone.utc)
CANDIDATE=dict(player='Context fixture',status='Out',position='WR',team='NE',stat_team='NE',
    relationship='teammate',unit='offense',participant_id='PartFi00')


def context_item(week=1,value=10,snaps=20,relationship='teammate'):
    game=dict(game_id=f'2026_{week:02}_NE_NYJ',season=2026,week=week,home_team='NYJ',away_team='NE',game_date=f'2026-09-{week+1:02}')
    team='NE' if relationship=='teammate' else 'NYJ'
    stat=dict(player_id='target',season=2026,week=week,team=team,passing_yards=value,
        rushing_yards=0,receiving_yards=0,receptions=0,source_provider='nflverse',
        source_sha256='a'*64,source_observed_at=NOW.isoformat())
    stat['source_record_sha256']=stat_row_sha256('nfl',stat)
    snap=dict(game_id=game['game_id'],season=2026,week=week,player_name='Context fixture',
        pfr_player_id='PartFi00',position='WR',team='NE',opponent='NYJ',offense_snaps=snaps,defense_snaps=snaps)
    digest=row_sha256(snap)
    snap.update(source_provider='nflverse',source_sha256='a'*64,source_record_sha256=digest,source_observed_at=NOW.isoformat())
    return dict(stat=stat,game=game,snaps=[snap])


def snapshot(rows=None):
    rows=rows or [context_item(),context_item(2,30,0),context_item(3,25)]
    return dict(observed_before=NOW,source_rows=rows,
        tenure_rows=[dict(snap=item['snaps'][0],game=item['game']) for item in rows if len(item['snaps'])==1 and item['snaps'][0]['offense_snaps']>0])


class Connection:
    def __init__(self,value):self.value=value
    async def fetchrow(self,query,*args):self.query,self.args=query,args;return self.value


async def read(value,candidate=None,prop='pass_yds',stamp=NOW):
    return await nfl_participation_split(Connection(value),'target',2024,date(2026,9,30),prop,15.5,'over',candidate or CANDIDATE,stamp)


@pytest.mark.asyncio
async def test_proved_positive_and_legacy_zero_keep_distinct_unknown_counts():
    result=await read(snapshot())
    assert result['active']==dict(games=2,mean=17.5,hit_rate=.5)
    assert result['absent']==dict(games=0,mean=None,hit_rate=None)
    assert result['unknown_games']==1 and result['evidence_version']=='recorded-participation-v3'
    assert result['sample_window']['unknown']==dict(oldest='2026-09-03',newest='2026-09-03')
    assert result['source_rows'][1]['classification']=='unknown'
    assert 'participant_id' not in result and 'tenure_rows' in result


@pytest.mark.asyncio
@pytest.mark.parametrize('change',[
    {'passing_yards':999},{'source_record_sha256':'b'*64},{'player_id':'other'},
    {'source_provider':'unknown'},{'source_sha256':'bad'},
    {'source_observed_at':'2026-10-01T00:00:00Z'},
    {'source_observed_at':'2026-08-01T00:00:00Z'},
])
async def test_target_tampering_or_wrong_chronology_withholds_comparison(change):
    value=deepcopy(snapshot());value['source_rows'][0]['stat'].update(change)
    assert await read(value) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('change',[
    {'offense_snaps':999},{'source_record_sha256':'b'*64},{'pfr_player_id':'Other00'},
    {'opponent':'DEN'},{'game_id':'wrong'},{'defense_snaps':None},
])
async def test_tenure_requires_actual_source_commitment_and_game_identity(change):
    value=deepcopy(snapshot());value['tenure_rows'][0]['snap'].update(change)
    assert await read(value) is None


@pytest.mark.asyncio
async def test_missing_duplicate_and_damaged_target_participation_are_unknown():
    for entries in ([],[context_item()['snaps'][0]]*2,
                    [context_item()['snaps'][0]|{'offense_snaps':999}]):
        value=deepcopy(snapshot());value['source_rows'][0]['snaps']=entries
        result=await read(value)
        assert result['active']['games']==1 and result['unknown_games']==2


@pytest.mark.asyncio
async def test_actual_game_mapping_binds_opponent_instead_of_mutable_enrichment():
    value=snapshot([context_item(relationship='opponent')])
    value['source_rows'][0]['stat']['opponent_team']='DEN'
    result=await read(value,CANDIDATE|dict(relationship='opponent',unit='defense',position='CB'))
    assert result['active']['games']==1
    value['source_rows'][0]['game']['home_team']='DEN'
    assert await read(value,CANDIDATE|dict(relationship='opponent',unit='defense',position='CB')) is None


@pytest.mark.asyncio
async def test_legacy_yard_hash_is_supported_but_cannot_prove_receptions():
    value=snapshot();stat=value['source_rows'][0]['stat']
    stat['source_record_sha256']=stat_row_sha256('nfl',stat,legacy_nfl=True)
    assert await read(value) is not None
    assert await read(value,prop='receptions') is None


@pytest.mark.asyncio
async def test_duplicate_targets_or_overflow_cannot_publish_an_aggregate():
    value=snapshot();value['source_rows']*=2
    assert await read(value) is None
    value=snapshot();value['tenure_rows']*=501
    assert await read(value) is None


@pytest.mark.asyncio
async def test_private_proof_retains_replay_inputs_without_unrelated_payloads():
    value=snapshot();original=deepcopy(value)
    value['source_rows'][0]['stat']['unrelated_blob']='x'*10000
    value['source_rows'][0]['game']['unrelated_blob']='x'*10000
    result=await read(value)
    assert 'unrelated_blob' not in result['source_rows'][0]['stat']
    assert 'unrelated_blob' not in result['source_rows'][0]['game']
    replay=dict(observed_before=result['observed_before'],source_rows=result['source_rows'],tenure_rows=result['tenure_rows'])
    assert await read(replay)==await read(original)


@pytest.mark.asyncio
async def test_receiving_supplement_keeps_manifest_and_acceptance_clock_for_replay():
    import json
    from sportsbet.quant.nfl_history_supplements import plan_supplements
    from tests.test_nfl_final_evidence import bundle, NOW as SOURCE_TIME
    from tests.test_nfl_history_supplements import game
    b=bundle();plan=plan_supplements(json.dumps(b),[],[game()],now=SOURCE_TIME)
    item,=plan['updates'];raw=b['participation'][0]
    snap=raw['row']|{k:raw[k] for k in ('source_provider','source_sha256','source_record_sha256','source_observed_at')}
    stat=item['stat_row']|dict(source_provider='nflverse_espn_supplement',source_sha256=item['source_sha256'],
        source_record_sha256=item['stat_record_sha256'],source_observed_at=item['observed_at'],
        supplement_manifest=item['manifest'],supplement_inserted_at=NOW.isoformat())
    row=dict(stat=stat,game=game(),snaps=[snap])
    value=dict(observed_before=NOW,source_rows=[row],tenure_rows=[dict(game=game(),snap=snap)])
    candidate=CANDIDATE|dict(stat_team='DEN',team='DEN',participant_id=snap['pfr_player_id'])
    async def run(receipt):
        return await nfl_participation_split(Connection(receipt),stat['player_id'],2024,date(2026,9,30),
            'rec_yds',.5,'under',candidate,NOW)
    result=await run(value)
    assert result['active']==dict(games=1,mean=0.,hit_rate=1.)
    assert result['source_rows'][0]['stat']['supplement_manifest']==item['manifest']
    assert await run(result)==result
    value['source_rows'][0]['stat']['supplement_inserted_at']='2026-10-01T00:00:00Z'
    assert await run(value) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('prop',['pass_tds','attempts','targets','completions','carries'])
async def test_uncommitted_auxiliary_props_never_gain_a_context_probability(prop):
    class NoQuery:
        async def fetchrow(self,*args):raise AssertionError('Unsupported context must not query')
    assert await nfl_participation_split(NoQuery(),'target',2024,date(2026,9,30),prop,1.5,'over',CANDIDATE,NOW) is None


@pytest.mark.asyncio
async def test_source_replayed_recent_window_separates_old_form_without_absence_inference():
    old=context_item(1,100)
    old['game'].update(game_id='2025_01_NE_NYJ',season=2025,game_date='2025-09-02')
    old['stat']['season']=2025
    old['stat']['source_record_sha256']=stat_row_sha256('nfl',old['stat'])
    snap=old['snaps'][0];snap.update(game_id='2025_01_NE_NYJ',season=2025)
    from sportsbet.prop.nfl_participation_evidence import SNAP_FIELDS
    snap['source_record_sha256']=row_sha256({k:snap[k] for k in SNAP_FIELDS})
    current=context_item(2,10);unknown=context_item(3,1000,0)
    value=snapshot([old,current,unknown]);before=deepcopy(value)
    result=await read(value)
    assert result['active']==dict(games=2,mean=55.,hit_rate=.5)
    assert result['recent_window']['active']==dict(games=1,mean=10.,hit_rate=0.)
    assert result['recent_window']['absent']==dict(games=0,mean=None,hit_rate=None)
    assert result['recent_window']['unknown_games']==1
    assert result['recent_window']['since']=='2026-08-31'
    assert await read(result)==result and value==before
