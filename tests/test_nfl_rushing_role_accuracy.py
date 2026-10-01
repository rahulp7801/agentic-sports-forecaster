from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from unittest.mock import patch

import pytest

from sportsbet.quant import nfl_rushing_role_accuracy as audit
from sportsbet.quant import model_selection_paper as paper

NOW=datetime(2026,10,3,12,tzinfo=timezone.utc)


def evidence(*,original=.8,candidate=.8,outcome=None,recorded=None):
    recorded=recorded or datetime.fromisoformat(audit.PROTOCOL['frozen_at'])+timedelta(minutes=1)
    selection=dict(prediction_id='p1',game_id='g1',player_id='id',prop_type='rush_yds',
        probability=original,market_probability=.5,game_start_time=(NOW-timedelta(days=1)).isoformat(),
        american_odds=-110)
    receipt=dict(sport='nfl',protocol=paper.PROTOCOL['policies']['raw_model'],
        recorded_at=recorded.isoformat(),prediction_id='p1',payload=json.dumps({'selection':selection}))
    row=dict(prediction_id='p1',outcome=outcome,outcome_observed_at=(NOW-timedelta(hours=1)).isoformat(),
        game_start_time=selection['game_start_time'],rushing_role_shadow=dict(generated_at=recorded.isoformat(),
            probability=candidate))
    return [receipt],[row]


def run(monkeypatch,receipts,predictions,probability=.8):
    monkeypatch.setattr(audit,'require_matching_runtime',lambda:None)
    monkeypatch.setattr(audit.paper,'audit_receipts',lambda *args:{'invalid_receipts':0})
    monkeypatch.setattr(audit.rush,'verified_shadow_probability',lambda row:probability)
    monkeypatch.setattr(audit.search.frozen.audit,'_verified_outcome',lambda row:row['outcome'])
    return audit.audit(receipts,predictions,NOW)


def test_fixed_original_and_candidate_rule_preserves_pending_and_price(monkeypatch):
    receipts,predictions=evidence()
    before=deepcopy((receipts,predictions))
    report=run(monkeypatch,receipts,predictions)
    assert report['coverage']['original_75']==1
    assert report['rule']['selected']==1 and report['rule']['pending']==1
    assert report['rule']['win_rate'] is None and not report['target_verified']
    assert report['selections'][0]['market_probability']==.5
    assert (receipts,predictions)==before
    assert run(monkeypatch,*evidence(candidate=.74),probability=.74)['rule']['selected']==0
    assert run(monkeypatch,*evidence(original=.74))['rule']['selected']==0


def test_settled_result_uses_matching_price_and_still_lacks_minimum_cohort(monkeypatch):
    receipts,predictions=evidence(outcome=True)
    report=run(monkeypatch,receipts,predictions)
    assert report['rule']['wins']==1 and report['rule']['decided']==1
    assert report['rule']['flat_stake_roi']==pytest.approx(100/110)
    assert report['rule']['candidate_minus_market_brier']==pytest.approx(.04-.25)
    assert report['status']=='awaiting_fixed_cohort' and not report['target_verified']
    predictions[0]['outcome_observed_at']=(NOW+timedelta(hours=1)).isoformat()
    assert run(monkeypatch,receipts,predictions)['rule']['pending']==1


def test_old_receipt_and_late_candidate_do_not_join_fixed_cohort(monkeypatch):
    old=datetime.fromisoformat(audit.PROTOCOL['frozen_at'])-timedelta(seconds=1)
    assert run(monkeypatch,*evidence(recorded=old))['coverage']['original_rushing_selections']==0
    receipts,predictions=evidence()
    predictions[0]['rushing_role_shadow']['generated_at']=(NOW+timedelta(seconds=1)).isoformat()
    report=run(monkeypatch,receipts,predictions)
    assert report['coverage']['original_75_with_candidate']==0
    assert report['rule']['selected']==0


def test_invalid_paper_receipt_stops_candidate_review(monkeypatch):
    receipts,predictions=evidence()
    monkeypatch.setattr(audit,'require_matching_runtime',lambda:None)
    monkeypatch.setattr(audit.paper,'audit_receipts',lambda *args:{'invalid_receipts':1})
    assert audit.audit(receipts,predictions,NOW)['status']=='invalid_source_evidence'
    with pytest.raises(ValueError,match='Duplicate'):
        audit.audit(receipts,predictions+predictions,NOW)


def test_runtime_matches_frozen_source_compression():
    with patch.object(audit.platform,'system',return_value='Windows'):
        with pytest.raises(ValueError,match='Linux CPython 3.12'):
            audit.require_matching_runtime()
