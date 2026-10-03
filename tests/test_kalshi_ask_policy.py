"""Displayed-ask candidates are frozen before scoring verified results."""
import copy
from datetime import timedelta
import json
from decimal import Decimal

import pytest

from sportsbet.quant import kalshi_ask_policy as policy
from sportsbet.quant.kalshi_market_cohort import digest
from tests.test_kalshi_pair_artifact import NOW, setup
from tests.test_kalshi_role_shadow_eval import AFTER, venue


def test_fixed_decision_uses_actual_side_ask_and_abstains_below_margin():
    offer = dict(ticker="T", milestone_id="G", player_target_id="P",
                 yes_ask=dict(cost="0.52", displayed_size="10"),
                 no_ask=dict(cost="0.50", displayed_size="12"))
    assert policy.decision(offer, {"model_over_probability": .8}) == dict(
        ticker="T", milestone_id="G", player_target_id="P", side="yes",
        displayed_ask="0.52", displayed_size="10",
        model_win_probability="0.8", gross_margin="0.28")
    assert policy.decision(offer, {"model_over_probability": .2})["side"] == "no"
    assert policy.decision(offer, {"model_over_probability": .5}) is None
    with pytest.raises(ValueError, match="Invalid"):
        policy.decision({**offer, "yes_ask": dict(cost="NaN", displayed_size="10")},
                        {"model_over_probability": .8})


def test_actual_decision_clock_is_read_after_every_candidate(tmp_path, monkeypatch):
    pair_path, _, _ = setup(tmp_path, monkeypatch)
    pair = json.loads(pair_path.read_text(encoding="utf-8"))
    pair.pop("ask_policy")
    decided = []

    def choose(*args):
        decided.append(True)
        return None

    class Clock:
        @staticmethod
        def now(tz):
            assert decided, "Decision clock was read before candidates were evaluated"
            return NOW + timedelta(seconds=3)

    monkeypatch.setattr(policy, "decision", choose)
    monkeypatch.setattr(policy, "datetime", Clock)
    receipt = policy.freeze(pair)
    assert receipt["frozen_at"] == (NOW+timedelta(seconds=3)).isoformat()
    assert receipt["below_margin"] == 1


def test_pregame_policy_replays_before_exact_venue_result(tmp_path, monkeypatch):
    pair_path, source_dir, market_dir = setup(tmp_path, monkeypatch)
    pair = json.loads(pair_path.read_text(encoding="utf-8"))
    archive = json.loads((market_dir/"market.json").read_text(encoding="utf-8"))
    assert policy.freeze(pair)["candidates_count"] == 0
    with pytest.raises(ValueError, match="timing window"):
        policy.freeze(pair, decided_at=policy.clock(pair["started_at"])+timedelta(seconds=31))
    pair["shadow"]["forecasts"][0]["model_over_probability"] = .8
    pair["shadow"]["forecasts_sha256"] = digest(pair["shadow"]["forecasts"])
    pair["forecasts_sha256"] = pair["shadow"]["forecasts_sha256"]
    pair["ask_policy"] = policy.freeze(pair)
    assert pair["ask_policy"]["candidates_count"] == 1
    assert pair["ask_policy"]["candidate_games"] == 1
    monkeypatch.setattr(policy.role, "build_report", lambda *args, **kwargs: pair["shadow"])
    report = policy.audit(pair, archive, source_dir, venue(pair["cohort"], "yes"), now=AFTER)
    assert report["candidate_result_counts"] == {"venue_verified": 1}
    assert Decimal(report["verified_subset_gross_unit_profit"]) == Decimal(".48")
    assert report["roi"] is None and report["edge_established"] is False
    assert report["zero_fee_unfilled_counterfactual"] is True
    changed = copy.deepcopy(pair)
    changed["ask_policy"]["candidates"][0]["side"] = "no"
    with pytest.raises(ValueError, match="receipt changed"):
        policy.audit(changed, archive, source_dir, venue(pair["cohort"]), now=AFTER)


def test_missing_venue_result_remains_in_candidate_denominator(tmp_path, monkeypatch):
    pair_path, source_dir, market_dir = setup(tmp_path, monkeypatch)
    pair = json.loads(pair_path.read_text(encoding="utf-8"))
    archive = json.loads((market_dir/"market.json").read_text(encoding="utf-8"))
    pair["shadow"]["forecasts"][0]["model_over_probability"] = .8
    pair["shadow"]["forecasts_sha256"] = digest(pair["shadow"]["forecasts"])
    pair["forecasts_sha256"] = pair["shadow"]["forecasts_sha256"]
    pair["ask_policy"] = policy.freeze(pair)
    monkeypatch.setattr(policy.role, "build_report", lambda *args, **kwargs: pair["shadow"])
    settled = venue(pair["cohort"])
    settled["evidence"]["pages"][0]["body"]["markets"] = []
    settled["evidence_sha256"] = digest(settled["evidence"])
    report = policy.audit(pair, archive, source_dir, settled, now=AFTER)
    assert report["candidates"] == 1 and report["verified_candidates"] == 0
    assert report["candidate_result_counts"] == {"not_returned": 1}
    assert report["verified_subset_displayed_cost"] == "0"
    assert report["complete"] is False
