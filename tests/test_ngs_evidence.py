from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from sportsbet.prop.ngs_evidence import load_ngs_evidence


def with_row_proofs(aggregate):
    from sportsbet.ingestion.ngs import METRIC_COLUMNS
    from sportsbet.ingestion.provenance import row_sha256
    kind=aggregate['source_url'].rsplit('ngs_',1)[1].split('.')[0]
    rows=[]
    for period in aggregate.get('sample_periods',[]):
        row=dict(season=period['season'],week=period['week'],team_abbr=period['team'],
                 player_gsis_id='00-0031234',player_position='QB' if kind=='passing' else 'WR',stat_type=kind)
        row.update({name:float(aggregate[name]) if aggregate.get(name) is not None else None
                    for name in METRIC_COLUMNS[kind]})
        digest=row_sha256(row)
        row.update(source_provider=aggregate['source_provider'],source_url=aggregate['source_url'],
                   source_sha256=aggregate['source_sha256'],source_record_sha256=digest,
                   source_observed_at=aggregate['source_observed_at'].isoformat())
        rows.append(row)
    refs=[]
    for year in sorted({r['season'] for r in rows}):
        ref=dict(version_id=year,season=year,stat_type=kind,source_sha256=aggregate['source_sha256'],
                 record_set_sha256='c'*64,recorded_at=aggregate['source_observed_at'].isoformat(),
                 normalization_version='ngs-db-precision-v2',row_count=len(rows))
        refs.append(ref)
        for row in rows:
            if row['season']==year:
                row.update(partition_version_id=year,record_set_sha256=ref['record_set_sha256'],
                    partition_available_at=ref['recorded_at'],normalization_version=ref['normalization_version'],
                    partition_rows=ref['row_count'])
    return aggregate | {'source_rows':rows,'partition_refs':refs}


class _Context:
    def __init__(self, value): self.value=value
    async def __aenter__(self): return self.value
    async def __aexit__(self, *args): return None


@pytest.mark.asyncio
async def test_ngs_evidence_uses_exact_game_week_and_only_prior_rows():
    conn=AsyncMock()
    conn.fetchval.return_value=datetime(2026,9,20,tzinfo=timezone.utc)
    conn.fetch=AsyncMock(return_value=[{'week':3}])
    conn.fetchrow=AsyncMock(return_value={
        'sample_weeks':4,'sample_periods':[{'season':2026,'week':2,'team':'LA'},{'season':2026,'week':1,'team':'LAR'},{'season':2025,'week':18,'team':'SEA'},{'season':2025,'week':17,'team':None}],'avg_separation':Decimal('2.71'),'avg_cushion':Decimal('5.3'),
        'avg_yac_above_expectation':Decimal('1.2'),'source_provider':'nflverse_ngs',
        'source_url':'https://github.com/nflverse/nflverse-data/releases/download/nextgen_stats/ngs_receiving.parquet',
        'source_sha256':'a'*64,'source_observed_at':datetime(2026,9,20,tzinfo=timezone.utc),
        'source_provider_count':1,'source_url_count':1,'source_version_count':1,
    })
    conn.fetchrow.return_value=with_row_proofs(conn.fetchrow.return_value)
    pool=MagicMock();pool.acquire.return_value=_Context(conn)
    result=await load_ngs_evidence(pool,player_gsis_id='00-0031234',season=2026,
        game_date=date(2026,9,20),team='LAR',prop_type='rec_yds')
    assert result and result['sample_weeks']==4 and result['cutoff_week']==3
    assert result['probability_adjusted'] is False
    assert result['metrics']['avg_separation']==2.71
    assert result['roster_team']=='LA' and result['sample_periods'][1]['team']=='LA'
    assert result['sample_periods'][-1]=={'season':2025,'week':17,'team':None}
    game_sql,*game_args=conn.fetch.await_args.args
    assert tuple(game_args)==(2026,date(2026,9,20),'LA') and 'game_date=$2' in game_sql
    evidence_sql,*evidence_args=conn.fetchrow.await_args.args
    assert tuple(evidence_args[:4])==('00-0031234','receiving',2026,3)
    assert evidence_args[4].utcoffset() is not None and evidence_args[5] is None
    assert 'week < $4' in evidence_sql and 'season BETWEEN $3-1 AND $3' in evidence_sql
    assert 'LIMIT 8' in evidence_sql and '00-0031234' not in evidence_sql


@pytest.mark.asyncio
async def test_ngs_evidence_fails_closed_without_unique_schedule_or_rows():
    conn=AsyncMock();conn.fetch=AsyncMock(return_value=[])
    pool=MagicMock();pool.acquire.return_value=_Context(conn)
    assert await load_ngs_evidence(pool,player_gsis_id='id',season=2026,
        game_date=date(2026,9,20),team='SEA',prop_type='pass_yds') is None
    conn.fetch.return_value=[{'week':2}]
    conn.fetchrow=AsyncMock(return_value={'sample_weeks':0})
    assert await load_ngs_evidence(pool,player_gsis_id='id',season=2026,
        game_date=date(2026,9,20),team='SEA',prop_type='pass_yds') is None
    assert await load_ngs_evidence(pool,player_gsis_id='id',season=2026,
        game_date=date(2026,9,20),team='SEA',prop_type='points') is None


@pytest.mark.asyncio
async def test_ngs_evidence_fails_closed_for_mixed_source_versions():
    conn=AsyncMock()
    conn.fetch=AsyncMock(return_value=[{'week':3}])
    conn.fetchrow=AsyncMock(return_value={
        'sample_weeks':2,'avg_separation':Decimal('2.5'),'avg_cushion':Decimal('5.0'),
        'avg_yac_above_expectation':Decimal('0.8'),'source_provider':'nflverse_ngs',
        'source_url':'https://github.com/nflverse/nflverse-data/releases/download/nextgen_stats/ngs_receiving.parquet',
        'source_sha256':'a'*64,'source_observed_at':datetime(2026,9,20,tzinfo=timezone.utc),
        'source_provider_count':1,'source_url_count':1,'source_version_count':2,
    })
    pool=MagicMock();pool.acquire.return_value=_Context(conn)
    assert await load_ngs_evidence(pool,player_gsis_id='00-0031234',season=2026,
        game_date=date(2026,9,20),team='LAR',prop_type='rec_yds') is None

@pytest.mark.asyncio
@pytest.mark.parametrize('invalid',['naive','late','oversized_sample','incomplete_source'])
async def test_tracking_rejects_invalid_observation_evidence(invalid):
    from datetime import timedelta
    cutoff=datetime(2026,9,20,tzinfo=timezone.utc)
    conn=AsyncMock();conn.fetch.return_value=[{'week':3}]
    conn.fetchrow.return_value={'sample_weeks':2,'avg_separation':2.5,'avg_cushion':5.0,'avg_yac_above_expectation':.8,
        'source_provider':'nflverse_ngs','source_url':'https://github.com/nflverse/nflverse-data/releases/download/nextgen_stats/ngs_receiving.parquet',
        'source_sha256':'a'*64,'source_observed_at':cutoff,'source_provider_count':1,'source_url_count':1,'source_version_count':1,'invalid_source_rows':0}
    pool=MagicMock();pool.acquire.return_value=_Context(conn)
    args=dict(player_gsis_id='00-0031234',season=2026,game_date=date(2026,9,20),team='SEA',prop_type='rec_yds',observed_before=cutoff)
    if invalid=='naive':
        args['observed_before']=cutoff.replace(tzinfo=None)
        with pytest.raises(ValueError,match='aware'):await load_ngs_evidence(pool,**args)
        pool.acquire.assert_not_called();return
    if invalid=='late':conn.fetchrow.return_value['source_observed_at']=cutoff+timedelta(microseconds=1)
    if invalid=='oversized_sample':conn.fetchrow.return_value['sample_weeks']=9
    if invalid=='incomplete_source':conn.fetchrow.return_value['invalid_source_rows']=1
    assert await load_ngs_evidence(pool,**args) is None


@pytest.mark.asyncio
async def test_tracking_binds_cutoff_before_window_selection_and_retains_it():
    cutoff=datetime(2026,9,20,tzinfo=timezone.utc)
    conn=AsyncMock();conn.fetch.return_value=[{'week':3}]
    conn.fetchrow.return_value={'sample_weeks':2,'sample_periods':[{'season':2026,'week':1,'team':'SEA'},{'season':2026,'week':2,'team':'SEA'}],'avg_time_to_throw':2.7,'avg_completed_air_yards':5.0,'avg_intended_air_yards':8.1,'aggressiveness':14.0,
        'source_provider':'nflverse_ngs','source_url':'https://github.com/nflverse/nflverse-data/releases/download/nextgen_stats/ngs_passing.parquet',
        'source_sha256':'a'*64,'source_observed_at':cutoff,'source_provider_count':1,'source_url_count':1,'source_version_count':1,'invalid_source_rows':0}
    conn.fetchrow.return_value=with_row_proofs(conn.fetchrow.return_value)
    pool=MagicMock();pool.acquire.return_value=_Context(conn)
    result=await load_ngs_evidence(pool,player_gsis_id='00-0031234',season=2026,game_date=date(2026,9,20),team='SEA',prop_type='pass_yds',observed_before=cutoff)
    assert result['observed_before']==cutoff.isoformat()
    assert result['evidence_version']=='ngs-row-commitment-v2' and 'source_rows' not in result
    sql,*args=conn.fetchrow.await_args.args
    assert args[-2]==cutoff and args[-1] is None
    assert sql.index('source_observed_at <= $5')<sql.index('LIMIT 8')
    assert sql.index('recorded_at <= $5')<sql.index('LIMIT 8')

@pytest.mark.parametrize('periods,count',[
    (None,1),([],1),([{'season':2026,'week':3,'team':'KC'}],1),
    ([{'season':2027,'week':1,'team':'KC'}],1),([{'season':2024,'week':1,'team':'KC'}],1),
    ([{'season':2026,'week':0,'team':'KC'}],1),([{'season':2025,'week':23,'team':'KC'}],1),
    ([{'season':2026,'week':1,'team':'bad'}],1),([{'season':2026,'week':True,'team':'KC'}],1),
    ([{'season':2026,'week':1,'team':'KC'}]*2,2),
])
def test_sample_periods_reject_future_duplicate_or_unbounded_values(periods,count):
    from sportsbet.prop.ngs_evidence import sample_periods
    with pytest.raises((ValueError,KeyError,TypeError)):sample_periods(periods,count,2026,3)


def test_sample_periods_decode_json_and_preserve_unknown_team():
    import json
    from sportsbet.prop.ngs_evidence import sample_periods
    value=[dict(season=2025,week=18,team=None),dict(season=2026,week=2,team='WSH')]
    assert sample_periods(json.dumps(value),2,2026,3)==[dict(season=2026,week=2,team='WAS'),dict(season=2025,week=18,team=None)]


@pytest.mark.asyncio
@pytest.mark.parametrize('damage',['missing','metric','digest','player','period','late','mean','version','available','refs'])
async def test_tracking_withholds_unproved_or_contradictory_metrics(damage):
    cutoff=datetime(2026,10,8,tzinfo=timezone.utc)
    aggregate=with_row_proofs({'sample_weeks':1,
        'sample_periods':[{'season':2026,'week':4,'team':'SEA'}],
        'avg_time_to_throw':2.75,'avg_completed_air_yards':6.2,
        'avg_intended_air_yards':7.1,'aggressiveness':14.5,
        'source_provider':'nflverse_ngs',
        'source_url':'https://github.com/nflverse/nflverse-data/releases/download/nextgen_stats/ngs_passing.parquet',
        'source_sha256':'a'*64,'source_observed_at':cutoff,
        'source_provider_count':1,'source_url_count':1,'source_version_count':1,'invalid_source_rows':0})
    source=aggregate['source_rows'][0]
    if damage=='missing':aggregate.pop('source_rows')
    elif damage=='metric':source['avg_time_to_throw']=9.0
    elif damage=='digest':source['source_record_sha256']='b'*64
    elif damage=='player':source['player_gsis_id']='00-0000001'
    elif damage=='period':source['week']=3
    elif damage=='late':source['source_observed_at']='2026-10-09T00:00:00+00:00'
    elif damage=='mean':aggregate['avg_time_to_throw']=9.0
    elif damage=='version':source['partition_version_id']+=1
    elif damage=='available':source['partition_available_at']='2026-10-09T00:00:00+00:00'
    elif damage=='refs':aggregate.pop('partition_refs')
    conn=AsyncMock();conn.fetch.return_value=[{'week':5}];conn.fetchrow.return_value=aggregate
    pool=MagicMock();pool.acquire.return_value=_Context(conn)
    assert await load_ngs_evidence(pool,player_gsis_id='00-0031234',season=2026,
        game_date=date(2026,10,11),team='SEA',prop_type='pass_yds',observed_before=cutoff) is None


@pytest.mark.parametrize('patch',[
    {'version_id':True},{'version_id':0},{'season':2024},{'stat_type':'rushing'},
    {'row_count':0},{'row_count':10001},{'normalization_version':'unknown'},
    {'source_sha256':'bad'},{'record_set_sha256':'bad'},
    {'recorded_at':'2026-10-09T00:00:00+00:00'},
    {'recorded_at':'2026-10-08T00:00:00'}, {'extra':'private'},
])
def test_pinned_partition_references_reject_ambiguous_or_late_versions(patch):
    from sportsbet.prop.ngs_evidence import partition_references
    cutoff=datetime(2026,10,8,tzinfo=timezone.utc)
    ref=dict(version_id=1,season=2026,stat_type='passing',source_sha256='a'*64,
        record_set_sha256='b'*64,row_count=2,normalization_version='ngs-db-precision-v2',
        recorded_at=cutoff.isoformat())
    with pytest.raises((ValueError,TypeError)):
        partition_references([ref|patch],2026,'passing',cutoff)
