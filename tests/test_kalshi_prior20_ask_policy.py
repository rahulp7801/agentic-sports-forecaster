"""A prior-20 ask-side hypothesis is committed before venue results."""
import copy
from datetime import timedelta
from decimal import Decimal
import json

import pytest

from sportsbet.quant import kalshi_ask_policy as role_policy
from sportsbet.quant import kalshi_prior20_ask_policy as prior_policy
from sportsbet.quant.kalshi_market_cohort import digest
from tests.test_kalshi_pair_artifact import NOW, setup
from tests.test_kalshi_role_shadow_eval import AFTER, venue


def challenger_pair(tmp_path, monkeypatch):
    pair_path, source_dir, market_dir = setup(tmp_path, monkeypatch)
    pair = json.loads(pair_path.read_text(encoding="utf-8"))
    forecast = pair["shadow"]["forecasts"][0]
    forecast["prior20_over_probability"] = .8
    pair["shadow"]["forecasts_sha256"] = digest(pair["shadow"]["forecasts"])
    pair["forecasts_sha256"] = pair["shadow"]["forecasts_sha256"]
    pair["ask_policy"] = role_policy.freeze(pair, decided_at=NOW+timedelta(seconds=3))
    pair["prior20_ask_policy"] = prior_policy.freeze(pair, decided_at=NOW+timedelta(seconds=3))
    archive = json.loads((market_dir/"market.json").read_text(encoding="utf-8"))
    return pair, archive, source_dir


def test_prior20_precommits_distinct_ask_side_and_scores_same_venue_result(tmp_path, monkeypatch):
    pair, archive, source_dir = challenger_pair(tmp_path, monkeypatch)
    receipt = pair["prior20_ask_policy"]
    assert receipt["comparator_model_version"] == prior_policy.role.COMPARATOR_VERSION
    assert receipt["model_forecasts"] == 1
    assert receipt["candidates_count"] == 1
    assert receipt["candidate_games"] == 1
    assert receipt["candidates"][0]["side"] == "yes"
    assert (receipt["model_unavailable"] + receipt["below_margin"]
            + receipt["one_per_player_game_excluded"]
            + receipt["candidates_count"] == len(pair["cohort"]["selections"]))
    assert pair["ask_policy"]["candidates_count"] == 0
    monkeypatch.setattr(prior_policy.role, "build_report", lambda *args, **kwargs: pair["shadow"])
    report = prior_policy.audit(pair, archive, source_dir,
                                venue(pair["cohort"], "yes"), now=AFTER)
    assert report["candidate_result_counts"] == {"venue_verified": 1}
    assert Decimal(report["verified_subset_gross_unit_profit"]) == Decimal(".48")
    assert report["roi"] is None and report["edge_established"] is False
    assert report["fees_included"] is False and report["fills_verified"] is False


def test_prior20_missing_result_and_changed_receipt_cannot_be_wins(tmp_path, monkeypatch):
    pair, archive, source_dir = challenger_pair(tmp_path, monkeypatch)
    monkeypatch.setattr(prior_policy.role, "build_report", lambda *args, **kwargs: pair["shadow"])
    result = venue(pair["cohort"])
    result["evidence"]["pages"][0]["body"]["markets"] = []
    result["evidence_sha256"] = digest(result["evidence"])
    report = prior_policy.audit(pair, archive, source_dir, result, now=AFTER)
    assert report["candidates"] == 1 and report["verified_candidates"] == 0
    assert report["candidate_result_counts"] == {"not_returned": 1}
    assert report["complete"] is False
    changed = copy.deepcopy(pair)
    changed["prior20_ask_policy"]["candidates"][0]["side"] = "no"
    with pytest.raises(ValueError, match="receipt changed"):
        prior_policy.audit(changed, archive, source_dir, result, now=AFTER)
    changed = copy.deepcopy(pair)
    changed["shadow"]["forecasts"][0].pop("prior20_over_probability")
    changed["shadow"]["forecasts_sha256"] = digest(changed["shadow"]["forecasts"])
    changed["forecasts_sha256"] = changed["shadow"]["forecasts_sha256"]
    with pytest.raises(ValueError, match="Missing frozen prior-20"):
        prior_policy.freeze(changed)

def test_two_policy_comparison_uses_only_common_verified_player_games(tmp_path, monkeypatch):
    pair, archive, source_dir = challenger_pair(tmp_path, monkeypatch)
    forecast = pair["shadow"]["forecasts"][0]
    forecast["model_over_probability"] = .8
    forecast["prior20_over_probability"] = .2
    pair["shadow"]["forecasts_sha256"] = digest(pair["shadow"]["forecasts"])
    pair["forecasts_sha256"] = pair["shadow"]["forecasts_sha256"]
    pair["ask_policy"] = role_policy.freeze(pair, decided_at=NOW+timedelta(seconds=3))
    pair["prior20_ask_policy"] = prior_policy.freeze(pair, decided_at=NOW+timedelta(seconds=3))
    monkeypatch.setattr(prior_policy.role, "build_report", lambda *args, **kwargs: pair["shadow"])
    result = venue(pair["cohort"], "yes")
    report = prior_policy.compare(pair, archive, source_dir, result, now=AFTER)
    assert report["common_player_game_exposures"] == 1
    assert report["role_only_exposures"] == report["prior20_only_exposures"] == 0
    assert report["common_same_contract"] == 1
    assert report["common_same_contract_and_side"] == 0
    assert report["both_venue_verified_exposures"] == report["both_verified_games"] == 1
    assert Decimal(report["prior20_minus_role_gross_profit_on_common_verified"]) == Decimal("-.98")
    assert report["prior20_minus_role_equal_game_game_cluster_95"] is None
    assert report["edge_established"] is False and report["roi"] is None
    result["evidence"]["pages"][0]["body"]["markets"] = []
    result["evidence_sha256"] = digest(result["evidence"])
    missing = prior_policy.compare(pair, archive, source_dir, result, now=AFTER)
    assert missing["common_player_game_exposures"] == 1
    assert missing["both_venue_verified_exposures"] == 0
    assert missing["unavailable_common_exposures"] == 1
    assert missing["prior20_minus_role_gross_profit_on_common_verified"] is None


def test_two_policy_comparison_keeps_distinct_selected_exposures(tmp_path, monkeypatch):
    pair, archive, source_dir = challenger_pair(tmp_path, monkeypatch)
    monkeypatch.setattr(prior_policy.role, "build_report", lambda *args, **kwargs: pair["shadow"])
    report = prior_policy.compare(pair, archive, source_dir,
                                  venue(pair["cohort"], "yes"), now=AFTER)
    assert report["role_candidates"] == 0 and report["prior20_candidates"] == 1
    assert report["common_player_game_exposures"] == 0
    assert report["prior20_only_exposures"] == 1
    assert report["both_venue_verified_exposures"] == 0
    assert report["prior20_minus_role_gross_profit_on_common_verified"] is None