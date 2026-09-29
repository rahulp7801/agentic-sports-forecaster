from copy import deepcopy
from datetime import datetime,timezone,timedelta,date
from decimal import Decimal
import json
import pytest
from sportsbet.model_contract import MODEL_VERSION,NFL_MODEL_VERSION,NFL_HISTORY_POLICY,NFL_HISTORY_FROZEN_AT,forecast_version_valid,model_version_for
from sportsbet.quant.nfl_history_supplements import plan_supplements
from sportsbet.ingestion.nfl_supplement_proof import valid_supplement,_sha
from sportsbet.prop.query_builder import PropQueryBuilder
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
