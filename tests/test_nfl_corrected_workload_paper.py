from datetime import datetime,timedelta
from unittest.mock import AsyncMock,MagicMock
import json

import pytest

from sportsbet.quant import nfl_corrected_workload_paper as paper
from sportsbet.quant import nfl_corrected_workload_shadow as candidate
from tests.test_nfl_corrected_workload_shadow import fixture


def test_earliest_supported_offer_is_fixed_before_history_or_result():
    payload,_=fixture()
    later=dict(payload,model_probability=.99,captured_at=(datetime.fromisoformat(payload['captured_at'])+timedelta(seconds=1)).isoformat())
    rows=[dict(id='z',payload=paper.encode(later)),dict(id='a',payload=paper.encode(payload))]
    selected=paper.earliest(rows)
    assert len(selected)==1
    assert selected[0]['prediction_id']=='a'
    assert selected[0]['model_probability']==payload['model_probability']


@pytest.mark.asyncio
async def test_capture_uses_saved_scan_and_read_only_history_without_provider(monkeypatch):
    payload,rows=fixture()
    capture=datetime.fromisoformat(payload['captured_at'])
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return capture+timedelta(seconds=2)
    monkeypatch.setattr(paper,'datetime',Clock)
    load=AsyncMock(return_value={(payload['player_id'],payload['prop_type']):rows})
    monkeypatch.setattr(paper,'load_histories',load)
    conn=MagicMock()
    conn.fetch=AsyncMock(return_value=[dict(id='prediction',payload=paper.encode(payload))])
    conn.execute=AsyncMock()
    conn.fetchval=AsyncMock(return_value='prediction')
    conn.transaction.return_value.__aenter__=AsyncMock(return_value=conn)
    conn.transaction.return_value.__aexit__=AsyncMock(return_value=None)
    pool=MagicMock()
    pool.acquire.return_value.__aenter__=AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__=AsyncMock(return_value=None)
    result=await paper.capture(pool,'a'*32)
    assert result['counts']=={'attempts':1,'predicted':1,'recorded':1}
    assert load.await_count==1
    assert conn.fetch.await_args.args==(paper.SCAN_SQL,'a'*32,paper.MAX_SCAN_ROWS+1)
    args=conn.fetchval.await_args.args
    assert args[0]==paper.INSERT_SQL and args[1]==paper.VERSION
    body=json.loads(args[-2])
    assert body['shadow']['model_version']==candidate.VERSION
    assert body['shadow']['status']=='predicted'
    assert body['shadow']['workload_source_commitment'] is False
    assert args[-1]==paper.digest(args[-2])


@pytest.mark.asyncio
async def test_paper_join_rejects_changed_forecast_and_keeps_server_time():
    payload,rows=fixture()
    payload['role_history_shadow_recorded_at']=(datetime.fromisoformat(payload['captured_at'])+timedelta(seconds=1)).isoformat()
    prediction=candidate.shadow_record(payload,rows)
    body=paper.encode(dict(version=paper.VERSION,
        forecast_sha256=paper.digest(paper.encode(payload)),shadow=prediction))
    at=datetime.fromisoformat(payload['captured_at'])+timedelta(seconds=2)
    receipt=dict(protocol=paper.VERSION,sport='nfl',game_id=payload['game_id'],
        player_id=payload['player_id'],prediction_id='one',decision_at=payload['captured_at'],
        valid_until=(datetime.fromisoformat(payload['quote_time'])+timedelta(seconds=300)).isoformat(),
        recorded_at=at.isoformat(),payload=body,
        payload_sha256=paper.digest(body),forecast=paper.encode(payload),outcome=None,
        outcome_source=None,outcome_ref=None,outcome_observed_at=None,actual_value=None,
        outcome_evidence=None)
    joined=paper._joined_row(receipt)
    assert joined['history_shadow_recorded_at']==at.isoformat()
    assert candidate.verified_recorded_shadow_probability(joined)==prediction['probability']
    changed=dict(receipt,forecast=paper.encode(payload|{'model_probability':.99}))
    with pytest.raises(ValueError,match='Invalid paper receipt'):
        paper._joined_row(changed)
    for change in (dict(decision_at=(at+timedelta(seconds=1)).isoformat()),
                   dict(valid_until=payload['game_start_time'])):
        with pytest.raises(ValueError,match='Invalid paper decision window'):
            paper._joined_row(dict(receipt,**change))

    conn=MagicMock()
    conn.fetch=AsyncMock(return_value=[receipt])
    conn.transaction.return_value.__aenter__=AsyncMock(return_value=conn)
    conn.transaction.return_value.__aexit__=AsyncMock(return_value=None)
    pool=MagicMock()
    pool.acquire.return_value.__aenter__=AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__=AsyncMock(return_value=None)
    report=await paper.report(pool)
    assert report['paper_receipts']==1 and report['invalid_paper_receipts']==0
    counts=report['markets']['receptions']['counts']
    assert counts['attempts']==1 and counts['valid_predictions']==1 and counts['pending']==1
    conn.fetch.return_value=[dict(receipt,payload_sha256='0'*64)]
    invalid=await paper.report(pool)
    assert invalid['paper_receipts']==invalid['invalid_paper_receipts']==1
    assert invalid['status']=='invalid_paper_receipts'
    assert invalid['markets']['receptions']['counts']['attempts']==0


@pytest.mark.asyncio
async def test_invalid_paper_receipt_cannot_leave_positive_support_status(monkeypatch):
    conn=MagicMock()
    conn.fetch=AsyncMock(return_value=[dict(payload='{}')])
    conn.transaction.return_value.__aenter__=AsyncMock(return_value=conn)
    conn.transaction.return_value.__aexit__=AsyncMock(return_value=None)
    pool=MagicMock()
    pool.acquire.return_value.__aenter__=AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__=AsyncMock(return_value=None)
    monkeypatch.setattr(paper.audit,'report_corrected_workload',lambda rows,sport:
        dict(status='collecting',markets={'rec_yds':dict(
            status='predictive_evidence_supported',promote=True)}))
    result=await paper.report(pool)
    assert result['invalid_paper_receipts']==1
    assert result['status']=='invalid_paper_receipts'
    assert result['markets']['rec_yds']['status']=='invalid_paper_receipts'
    assert result['markets']['rec_yds']['promote'] is False
