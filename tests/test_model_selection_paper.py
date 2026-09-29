from collections import Counter
from copy import deepcopy
from datetime import timedelta
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from sportsbet.quant import model_selection_paper as paper
from sportsbet.quant import cross_book_paper as existing
from tests.test_cross_book_paper import rows, NOW


def receipt(policy="raw_model"):
    candidates = paper.prepare(rows(), "nfl", NOW+timedelta(seconds=1))
    return next(r for r in candidates if r["protocol"] == paper.PROTOCOL["policies"][policy]) | {
        "recorded_at": NOW+timedelta(seconds=2)}


def test_both_policies_have_distinct_private_protocols_and_exact_controls():
    prepared=paper.prepare(rows(),"nfl",NOW+timedelta(seconds=1))
    assert len(prepared)==2
    assert len({r["protocol"] for r in prepared})==2
    for r in prepared:
        body=json.loads(r["payload"])
        assert body["selection"]["opposite_american_odds"] == -170
        assert body["selection"]["prediction_id"] == "aOver"
        assert body["selection"]["opposite_evidence_origin"] == "retained_forecast"
        assert all("outcome" not in x and "availability" not in x for x in body["evidence"])
        assert r["protocol"] != existing.VERSION


def test_prefreeze_expired_and_postgame_cannot_record():
    assert paper.prepare(rows(),"nfl",NOW-timedelta(days=1))==[]
    assert paper.prepare(rows(),"nfl",NOW+timedelta(minutes=5))==[]
    assert paper.prepare(rows(),"nfl",NOW+timedelta(days=2))==[]


@pytest.mark.parametrize("field", ["history_policy_version", "recommendation_policy_version"])
def test_policy_changes_fail_closed(field):
    data=rows();data[0][field]="changed"
    with pytest.raises(ValueError,match="policy"):
        paper.prepare(data,"nfl",NOW+timedelta(seconds=1))


def test_changed_dependency_blocks_recording(monkeypatch):
    monkeypatch.setattr(paper,"FROZEN_DIGESTS",{})
    with pytest.raises(ValueError,match="dependencies changed"):
        paper.prepare(rows(),"nfl",NOW+timedelta(seconds=1))


def test_older_model_and_prefreeze_inputs_do_not_enter_new_cohort():
    data=rows()
    for r in data:r["model_version"]="empirical-jeffreys-v4"
    assert paper.prepare(data,"nfl",NOW+timedelta(seconds=1))==[]
    data=rows()
    for r in data:r["quote_time"]=(NOW-timedelta(days=1)).isoformat()
    assert paper.prepare(data,"nfl",NOW+timedelta(seconds=1))==[]


def test_future_capture_fails_closed():
    data=rows();data[0]["captured_at"]=(NOW+timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError,match="Future"):
        paper.prepare(data,"nfl",NOW+timedelta(seconds=1))


@pytest.mark.parametrize("change",["late","body","identity","deadline","implementation","forecast","duplicate","policy"])
def test_tampered_receipts_fail_audit(change):
    value=receipt();predictions=rows();receipts=[value]
    if change=="late":value["recorded_at"]=NOW+timedelta(minutes=6)
    if change=="body":value["payload"]+=" "
    if change=="identity":value["player_id"]="other"
    if change=="deadline":value["valid_until"]+=timedelta(minutes=1)
    if change=="implementation":
        body=json.loads(value["payload"]);body["commitments"]["implementation"]="changed"
        value["payload"]=existing.encode(body);value["payload_sha256"]=existing.digest(body)
    if change=="forecast":predictions[0]["model_probability"] = .99
    if change=="duplicate":receipts.append(deepcopy(value))
    if change=="policy":
        body=json.loads(value["payload"]);body["policy"]="market_prior80"
        value["payload"]=existing.encode(body);value["payload_sha256"]=existing.digest(body)
    report=paper.audit_receipts(receipts,predictions,"nfl","raw_model",NOW+timedelta(days=3))
    assert report["status"]=="invalid_evidence" and report["invalid_receipts"]>=1
    assert not report["promote"]


def test_only_authenticated_outcomes_observed_by_audit_time_enter_returns(monkeypatch):
    value=receipt();predictions=rows()
    for r in predictions:r.update(outcome=True,outcome_observed_at=(NOW+timedelta(days=3)).isoformat())
    assert paper.audit_receipts([value],predictions,"nfl","raw_model",NOW+timedelta(days=4))["cohort_pending"]==1
    monkeypatch.setattr(paper.search.frozen.audit,"_verified_outcome",lambda r:r.get("outcome"))
    assert paper.audit_receipts([value],predictions,"nfl","raw_model",NOW+timedelta(days=2))["cohort_pending"]==1
    r=paper.audit_receipts([value],predictions,"nfl","raw_model",NOW+timedelta(days=4))
    assert r["decided"]==1 and r["scores"]["model"]["mean"]==1.5
    assert r["scores"]["always_under"]["mean"]==-1
    assert r["scores"]["model_minus_under"]["mean"]==2.5


def entries(count=50,players=2):
    return [dict(selection=dict(game_id=f"game-{game:03}",game_start_time=(NOW+timedelta(days=game)).isoformat(),
        direction="over",american_odds=100,opposite_american_odds=-110,probability=.75,market_probability=.5),outcome=True)
        for game in range(count) for _ in range(players)]


def test_fixed_first_fifty_games_cannot_be_extended_to_improve_result():
    data=entries(51)
    for r in data[-2:]:r["outcome"]=False
    report=paper.summarize(list(reversed(data)),Counter(),"nfl","raw_model",NOW+timedelta(days=60))
    assert report["review_cohort_games"]==50 and report["decided"]==100
    assert report["excluded_later_or_unstarted_receipts"]==2
    assert "game-050" not in report["review_game_ids"]
    assert report["status"]=="review_required" and report["cohort_closed"]
    assert not report["promote"]


def test_pending_early_game_cannot_be_replaced_by_later_winner():
    data=entries(51);data[0]["outcome"]=None
    r=paper.summarize(data,Counter(),"nfl","raw_model",NOW+timedelta(days=60))
    assert r["status"]=="awaiting_cohort_settlement" and r["cohort_pending"]==1
    assert r["decided"]==99 and not r["cohort_closed"]


def test_small_closed_cohort_does_not_expand_until_threshold_met():
    r=paper.summarize(entries(100,1),Counter(),"nfl","raw_model",NOW+timedelta(days=120))
    assert r["review_cohort_games"]==50 and r["decided"]==50
    assert r["status"]=="insufficient_fixed_cohort"


def test_unstarted_games_cannot_close_cohort():
    r=paper.summarize(entries(),Counter(),"nfl","raw_model",NOW+timedelta(days=48))
    assert r["review_cohort_games"]==49 and r["status"]=="collecting_fixed_cohort"


def test_constant_under_advantage_must_be_exceeded_for_review():
    data=entries()
    for r in data:r["selection"]["direction"]="under"
    report=paper.summarize(data,Counter(),"nfl","raw_model",NOW+timedelta(days=60))
    assert report["scores"]["model"]["mean"]==1
    assert report["scores"]["model_minus_under"]["mean"]==0
    assert report["status"]=="edge_not_demonstrated"


@pytest.mark.asyncio
async def test_empty_work_never_acquires_database(monkeypatch):
    pool=AsyncMock();monkeypatch.setattr(paper,"prepare",lambda *_:[])
    await paper.record(pool,[],"nfl");pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_record_is_atomic_bounded_append_only(monkeypatch):
    prepared=[receipt(),receipt("market_prior80")]
    monkeypatch.setattr(paper,"prepare",lambda *_:prepared)
    conn=MagicMock();conn.execute=AsyncMock();conn.fetchval=AsyncMock()
    tx=MagicMock();tx.__aenter__=AsyncMock();tx.__aexit__=AsyncMock(return_value=False)
    conn.transaction.return_value=tx
    acquire=MagicMock();acquire.__aenter__=AsyncMock(return_value=conn);acquire.__aexit__=AsyncMock(return_value=False)
    pool=MagicMock();pool.acquire.return_value=acquire
    await paper.record(pool,rows(),"nfl")
    assert conn.fetchval.await_count==2
    assert all(call.args[0]==existing.INSERT_SQL for call in conn.fetchval.await_args_list)
    conn.execute.assert_awaited_once_with("SET LOCAL statement_timeout='2s'")
    assert {call.args[1] for call in conn.fetchval.await_args_list} == set(paper.PROTOCOL["policies"].values())


@pytest.mark.asyncio
async def test_failure_cannot_erase_production_forecasts(monkeypatch):
    monkeypatch.setattr(paper,"prepare",lambda *_:(_ for _ in ()).throw(ValueError("failed research")))
    await paper.record(AsyncMock(),rows(),"nfl")
