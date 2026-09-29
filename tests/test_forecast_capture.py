from copy import deepcopy
from datetime import datetime,timezone

import pytest

from sportsbet.quant.forecast_capture import restore_capture

NOW=datetime(2026,9,29,tzinfo=timezone.utc)


def fixture():
    evidence=dict(source_observed_at='2026-09-20T10:00:00+00:00',metrics={'avg_separation':2.5})
    record=dict(game_id='game',player_id='00-0031234',player='Fixture',sport='nfl',prop_type='rec_yds',line=50.5,direction='over',sportsbook='book',american_odds=-110,model_version='empirical-jeffreys-v4',next_gen_stats=evidence,quote_time='2026-09-20T10:00:00+00:00',model_sample_size=30,model_mean_stat=60.0,model_probability=.6,captured_at='2026-09-20T10:00:02+00:00',model_generated_at='2026-09-20T10:00:02+00:00',game_start_time='2026-09-20T18:00:00+00:00')
    from sportsbet.quant.forecast_capture import FIELDS
    signal={k:record[v] for k,v in FIELDS.items()}|dict(id='id',game_start_time=record['game_start_time'])
    return dict(generated_at='2026-09-20T10:00:03+00:00',signals=[signal]),{'id':record}


def test_restore_only_capture_metadata_preserving_original_snapshot_and_source():
    snapshot,records=fixture();original=deepcopy(snapshot);sources=deepcopy(records)
    plan=restore_capture(snapshot,records,now=NOW)
    assert snapshot==original and records==sources and plan['unresolved']==[]
    assert len(plan['restored'])==1 and plan['payload']['generated_at']==snapshot['generated_at']
    result=plan['payload']['signals'][0]
    assert result.pop('captured_at')==records['id']['captured_at'] and result==snapshot['signals'][0]
    plan=restore_capture(snapshot,records,now=NOW)
    assert restore_capture(plan['payload'],records,now=NOW)['restored']==[]


@pytest.mark.parametrize('field,value',[('line',51.5),('player','Other'),('player_id','00-0000001'),('model_version','other'),('true_prob',.7),('sample_size',31),('game_start_time','2026-09-20T19:00:00+00:00'),('next_gen_stats',{'source_observed_at':'2026-09-20T11:00:00+00:00'})])
def test_mismatched_snapshot_never_borrows_capture(field,value):
    snapshot,records=fixture();snapshot['signals'][0][field]=value
    plan=restore_capture(snapshot,records,now=NOW)
    assert plan['restored']==[] and plan['payload']==snapshot


@pytest.mark.parametrize('mode',['missing','late_source','future_capture','after_game','generation_mismatch','naive','late_cutoff'])
def test_unverifiable_capture_remains_missing(mode):
    snapshot,records=fixture();record=records['id']
    if mode=='missing':records={}
    if mode=='late_source':record['next_gen_stats']['source_observed_at']='2026-09-20T10:00:03+00:00'
    if mode=='future_capture':record['captured_at']=record['model_generated_at']='2026-10-01T10:00:00+00:00'
    if mode=='after_game':record['captured_at']=record['model_generated_at']=record['game_start_time']
    if mode=='generation_mismatch':record['model_generated_at']='2026-09-20T10:00:01+00:00'
    if mode=='naive':record['captured_at']='2026-09-20T10:00:02'
    if mode=='late_cutoff':record['next_gen_stats']['observed_before']='2026-09-20T10:00:03+00:00'
    assert restore_capture(snapshot,records,now=NOW)['restored']==[]


def test_existing_capture_is_never_overwritten_even_when_wrong():
    snapshot,records=fixture();snapshot['signals'][0]['captured_at']='invalid'
    plan=restore_capture(snapshot,records,now=NOW)
    assert plan['restored']==[] and plan['payload']==snapshot


def test_invalid_record_commitment_cannot_leave_a_partial_capture_edit():
    snapshot,records=fixture();records['id']['invalid']=float('nan')
    plan=restore_capture(snapshot,records,now=NOW)
    assert plan['restored']==[] and plan['unresolved']==['id'] and plan['payload']==snapshot
