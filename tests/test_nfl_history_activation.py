from copy import deepcopy
import asyncio
from datetime import datetime,timezone,timedelta,date
from decimal import Decimal
import json
import os
import asyncpg
import pytest
from sportsbet.model_contract import MODEL_VERSION,NFL_MODEL_VERSION,NFL_HISTORY_POLICY,NFL_HISTORY_FROZEN_AT,forecast_version_valid,model_version_for
from sportsbet.quant.nfl_history_supplements import plan_supplements
from sportsbet.ingestion.nfl_supplement_proof import valid_supplement,_sha
from sportsbet.prop.query_builder import PropQueryBuilder
from sportsbet.prop.nfl_core_source_proof import attach_source_proof,verify_source_rows
from sportsbet.ingestion.provenance import stat_row_sha256
from sportsbet.graph.models import PropParams
from tests.test_nfl_final_evidence import bundle,NOW
from tests.test_nfl_history_supplements import game


def test_version_and_prospective_cutoff_do_not_relabel_retained_forecasts():
    cutoff=datetime.fromisoformat(NFL_HISTORY_FROZEN_AT)
    p=dict(sport='nfl',model_version=NFL_MODEL_VERSION,history_policy_version=NFL_HISTORY_POLICY)
    assert model_version_for('nfl')==NFL_MODEL_VERSION
    assert forecast_version_valid(p,cutoff)
    assert not forecast_version_valid(p,cutoff-timedelta(microseconds=1))
    assert not forecast_version_valid(p|dict(sport='nba'),cutoff)
    assert not forecast_version_valid(p|dict(history_policy_version='unknown'),cutoff)
    assert forecast_version_valid(p|dict(model_version=MODEL_VERSION),cutoff)


def test_corrected_query_filters_receipts_before_selecting_recent_games():
    observed=datetime.fromisoformat(NFL_HISTORY_FROZEN_AT)
    params=PropParams(sport='nfl',player_id='00-0036422',season=2024,game_id='future',prop_type='rec_yds',
        line=Decimal('0.5'),filters={},as_of_date=date(2026,9,30),observed_before=observed,last_n_games=40)
    sql,args=PropQueryBuilder.build(params)
    assert sql.count('FROM nfl_effective_receiving_gamelogs AS player_stats')==2
    assert sql.count('supplement_inserted_at <=')==2 and observed in args
    for update in (dict(prop_type='pass_yds'),dict(observed_before=None)):
        raw,_=PropQueryBuilder.build(params.model_copy(update=update))
        assert 'nfl_effective_receiving_gamelogs' not in raw
    with pytest.raises(ValueError):
        PropQueryBuilder.build(params.model_copy(update=dict(observed_before=NOW.replace(tzinfo=None))))


@pytest.mark.parametrize('prop_type', ['pass_yds', 'rush_yds'])
def test_core_history_proof_checks_the_same_last_40_rows(prop_type):
    observed=datetime.fromisoformat(NFL_HISTORY_FROZEN_AT)
    params=PropParams(sport='nfl',player_id='00-0036422',season=2024,game_id='future',
        prop_type=prop_type,line=Decimal('0.5'),filters={},as_of_date=date(2026,9,30),
        observed_before=observed,last_n_games=40)
    original,original_args=PropQueryBuilder.build(params)
    assert 'history_source_verified' not in original
    sql,args=attach_source_proof(original,original_args,params)
    assert sql.count('FROM player_stats')==2
    assert 'BOOL_AND(source_provider' in sql
    assert 'JSONB_AGG(JSONB_BUILD_OBJECT' in sql
    assert 'history_source_rows' in sql
    assert 'source_observed_at IS NOT NULL AND source_observed_at <= $6' in sql
    assert args==(params.player_id,2024,.5,date(2026,9,30),40,observed)
    assert sql.index('history_source_verified') < sql.index('FROM player_stats')
    assert 'source_observed_at <=' not in sql.split('WHERE ',1)[1]
    with pytest.raises(ValueError):
        attach_source_proof(original,original_args,
            params.model_copy(update={'observed_before':observed.replace(tzinfo=None)}))


@pytest.mark.skipif(not os.environ.get('SPORTSBET_TEST_DATABASE_URL'),
    reason='Disposable PostgreSQL URL not set')
def test_core_history_aggregate_replays_row_digest_in_postgres():
    async def exercise():
        url=os.environ['SPORTSBET_TEST_DATABASE_URL'].replace('+psycopg','')
        conn=await asyncpg.connect(url)
        try:
            await conn.execute('''CREATE TEMP TABLE player_stats (
                player_id text,season smallint,week smallint,team text,
                passing_yards smallint,rushing_yards smallint,receiving_yards smallint,
                receptions smallint,source_provider text,source_sha256 text,
                source_record_sha256 text,source_observed_at timestamptz)''')
            await conn.execute('''CREATE TEMP TABLE games (
                season smallint,week smallint,home_team text,away_team text,
                game_date date)''')
            stat={'player_id':'00-0036422','season':2024,'week':1,'team':'KC',
                'passing_yards':240,'rushing_yards':15,'receiving_yards':0,
                'receptions':0}
            digest=stat_row_sha256('nfl',stat)
            await conn.execute('''INSERT INTO player_stats VALUES
                ($1,$2,$3,$4,$5,$6,$7,$8,'nflverse',$9,$10,$11)''',
                *stat.values(),'a'*64,digest,datetime(2024,9,9,tzinfo=timezone.utc))
            await conn.execute("INSERT INTO games VALUES (2024,1,'KC','BAL','2024-09-08')")
            params=PropParams(sport='nfl',player_id=stat['player_id'],season=2024,
                game_id='future',prop_type='pass_yds',line=Decimal('250.5'),filters={},
                as_of_date=date(2024,10,1),
                observed_before=datetime(2024,9,30,tzinfo=timezone.utc),last_n_games=40)
            sql,args=attach_source_proof(*PropQueryBuilder.build(params),params)
            row=await conn.fetchrow(sql,*args)
            assert row['total']==1 and row['successes']==0
            assert row['history_source_verified'] is True
            assert verify_source_rows(row['history_source_rows'],row['total'])
            await conn.execute('UPDATE player_stats SET passing_yards=400')
            changed=await conn.fetchrow(sql,*args)
            assert changed['history_source_verified'] is True
            assert changed['successes']==1
            assert not verify_source_rows(changed['history_source_rows'],changed['total'])
        finally:
            await conn.close()
    asyncio.run(exercise())


def supplement():
    return plan_supplements(json.dumps(bundle()),[],[game()],now=NOW)['updates'][0]


def test_retained_nfl_proof_validates_source_and_identity():
    s=supplement()
    assert valid_supplement(s['stat_row'],s['manifest'],s['source_sha256'],s['observed_at'],s['manifest']['game'])


@pytest.mark.parametrize('change',['stat','manifest','event','participation','url','future','policy'])
def test_tampered_nfl_proof_fails_even_with_recomputed_outer_hash(change):
    s=deepcopy(supplement());m=s['manifest'];g=deepcopy(m['game'])
    if change=='stat':s['stat_row']['receptions']=1
    if change=='manifest':m['explicit_source']['gsis_player_id']='00-0000000'
    if change=='event':g['provider_event_id']='999'
    if change=='participation':m['explicit_source']['participation']['row']['offense_snaps']=0
    if change=='url':m['explicit_source']['sources'][0]['url']='https://evil.example/'
    if change=='future':m['explicit_source']['sources'][0]['observed_at']='2099-01-01T00:00:00Z'
    if change=='policy':m['policy_version']='unknown'
    m['explicit_source_sha256']=_sha(m['explicit_source'])
    assert not valid_supplement(s['stat_row'],m,_sha(m),s['observed_at'],g)
