from copy import deepcopy
from datetime import datetime,timedelta,timezone
from unittest.mock import AsyncMock
import json
import pytest
from sportsbet.quant import cross_book_paper as paper
from sportsbet.quant.market_baseline import paired_market_baseline
from sportsbet.scan import quotes_from_event
from tests.test_cross_book_forward import row

NOW=datetime(2026,9,30,1,tzinfo=timezone.utc)


def rows():
    base=row(NOW)
    event=dict(id=base['game_id'],commence_time=base['game_start_time'],
        home_team='Home',away_team='Away',bookmakers=[])
    for book,prices in [('a',(150,-170)),('b',(-110,-110))]:
        event['bookmakers'].append(dict(key=book,last_update=base['quote_time'],markets=[dict(
            key='player_reception_yds',last_update=base['quote_time'],outcomes=[dict(
                name=side,description=base['player'],point=base['line'],price=price)
                for side,price in zip(('Over','Under'),prices)])]))
    quotes=quotes_from_event(event,'nfl');result=[]
    for q in quotes:
        result.append(base|dict(prediction_id=q.sportsbook+q.side,sportsbook=q.sportsbook,
            direction=q.side.lower(),american_odds=q.price,quote_source_sha256=q.source_sha256,
            quote_source_record_sha256=q.source_record_sha256,**paired_market_baseline(q,quotes)))
    return result


def receipt():
    prepared=paper.prepare(rows(),'nfl',NOW+timedelta(seconds=1))
    assert len(prepared)==1
    return prepared[0]|dict(recorded_at=NOW+timedelta(seconds=2))


def test_genuine_price_pair_produces_private_immutable_receipt():
    value=receipt();body=json.loads(value['payload'])
    assert value['prediction_id']=='aOver'
    assert body['selection']['reference_probability']==.5
    assert body['selection']['offered_market_probability']<.5
    assert body['selection']['estimated_return']==.25
    assert all('outcome' not in r and 'availability' not in r for r in body['evidence'])
    result=paper.audit_receipts([value],rows(),'nfl',NOW+timedelta(minutes=1))
    assert result['valid_receipts']==1 and result['pending']==1
    assert result['decided']==0 and result['promote'] is False


def test_before_freeze_and_expired_prices_cannot_be_recorded():
    assert paper.prepare(rows(),'nfl',NOW-timedelta(days=1))==[]
    assert paper.prepare(rows(),'nfl',NOW+timedelta(minutes=5))==[]
    assert paper.prepare(rows(),'nfl',NOW+timedelta(days=2))==[]


@pytest.mark.parametrize('change',['late','body','identity','deadline','implementation','forecast','duplicate'])
def test_audit_rejects_forged_or_changed_receipts(change):
    value=receipt();predictions=rows();receipts=[value]
    if change=='late':value['recorded_at']=NOW+timedelta(minutes=6)
    if change=='body':value['payload']+=' '
    if change=='identity':value['player_id']='different'
    if change=='deadline':value['valid_until']+=timedelta(hours=1)
    if change=='implementation':
        body=json.loads(value['payload']);body['implementation']['paper']='changed'
        value['payload']=paper.encode(body);value['payload_sha256']=paper.digest(body)
    if change=='forecast':predictions[0]['model_probability']=.99
    if change=='duplicate':receipts.append(deepcopy(value))
    report=paper.audit_receipts(receipts,predictions,'nfl',NOW+timedelta(hours=1))
    assert report['invalid_receipts']>=1
    assert report['status']=='invalid_evidence' and not report['promote']


def test_only_authenticated_settlements_enter_paper_return(monkeypatch):
    value=receipt();predictions=rows()
    for prediction in predictions:
        prediction.update(outcome=True,outcome_observed_at=(NOW+timedelta(days=2)).isoformat())
    assert paper.audit_receipts([value],predictions,'nfl',NOW+timedelta(days=3))['pending']==1
    monkeypatch.setattr(paper.candidate.audit,'_verified_outcome',lambda r:r.get('outcome'))
    assert paper.audit_receipts([value],predictions,'nfl',NOW+timedelta(days=1))['pending']==1
    report=paper.audit_receipts([value],predictions,'nfl',NOW+timedelta(days=3))
    assert report['decided']==1 and report['wins']==1
    assert report['flat_stake_roi']==1.5 and report['settled_games']==1
    assert report['roi_game_cluster_95'] is None


@pytest.mark.asyncio
async def test_expired_or_prefreeze_work_does_not_acquire_database(monkeypatch):
    pool=AsyncMock()
    monkeypatch.setattr(paper,'prepare',lambda *_:[])
    await paper.record(pool,rows(),'nfl')
    pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_research_failure_does_not_erase_main_forecasts(monkeypatch):
    monkeypatch.setattr(paper,'prepare',lambda *_:(_ for _ in ()).throw(ValueError('bad research')))
    await paper.record(AsyncMock(),rows(),'nfl')



def test_ledger_added_shadow_receipt_metadata_does_not_change_price_evidence():
    value=receipt();predictions=rows()
    for prediction in predictions:
        prediction.update(history_shadow_recorded_at=NOW.isoformat(),history_shadow_input_sha256='a'*64,
            role_history_shadow_input_sha256='b'*64)
    report=paper.audit_receipts([value],predictions,'nfl',NOW+timedelta(minutes=1))
    assert report['valid_receipts']==1 and report['pending']==1
