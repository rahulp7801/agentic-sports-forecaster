"""Prospective series counts distinct games, complete outcomes and replayed pairs."""
import copy
from datetime import timedelta
from pathlib import Path

import pytest

from sportsbet.quant import kalshi_role_shadow as v1
from sportsbet.quant import kalshi_role_shadow_v2 as v3
from sportsbet.quant import kalshi_pair_capture as capture
from sportsbet.quant import kalshi_pair_series_eval as series
from sportsbet.quant.kalshi_market_cohort import digest
from tests.test_kalshi_role_shadow import fixture
from tests.test_kalshi_role_shadow_eval import AFTER, venue
from tests.test_kalshi_pair_capture import FRESH
from tests.test_kalshi_role_shadow_v2 import manifest


def case(monkeypatch):
    market, _, stats, snaps, identity = fixture()
    monkeypatch.setattr(v3, "load_sources", lambda *args: (stats, snaps))
    monkeypatch.setattr(v1, "identity_index", lambda *args: identity)
    pair = capture.capture(
        market, Path("unused"), started_at=FRESH,
        completed_at=FRESH + timedelta(seconds=2),
        source_manifest=manifest())
    return dict(pair=pair, market_archive=market, source_dir=Path("unused"),
                settlements=venue(pair["cohort"]))


def test_one_authenticated_pair_has_one_game_and_no_skill_or_edge(monkeypatch):
    item = case(monkeypatch)
    report = series.aggregate([item], now=AFTER)
    assert report["cohort_count"] == 1
    assert report["model_version"] == item["pair"]["shadow"]["protocol"]
    assert report["selected_contracts"] == report["forecast_contracts"] == 1
    assert report["selected_games"] == report["verified_games"] == 1
    assert report["result_states"] == {"venue_verified": 1}
    assert report["complete"] is True
    assert report["minimum_50_independent_games_met"] is False
    assert report["forecast_skill_gate_met"] is False
    assert report["edge_established"] is False and report["qualified_picks"] == 0
    assert report["market_comparison"]["model_minus_market_brier_game_cluster_95"] is None


def test_overlapping_pairs_fail_even_when_each_receipt_is_valid(monkeypatch):
    item = case(monkeypatch)
    with pytest.raises(ValueError, match="Overlapping game cohorts"):
        series.aggregate([item, copy.deepcopy(item)], now=AFTER)


def test_missing_result_retains_denominator_and_blocks_skill(monkeypatch):
    item = case(monkeypatch)
    settlement = copy.deepcopy(item["settlements"])
    settlement["evidence"]["pages"][0]["body"]["markets"] = []
    settlement["evidence_sha256"] = digest(settlement["evidence"])
    item["settlements"] = settlement
    report = series.aggregate([item], now=AFTER)
    assert report["forecast_contracts"] == 1
    assert report["verified_forecasts"] == report["verified_games"] == 0
    assert report["result_states"] == {"not_returned": 1}
    assert report["complete"] is False
    assert report["forecast_skill_gate_met"] is False


def test_changed_model_or_price_fails_replay(monkeypatch):
    item = case(monkeypatch)
    changed = copy.deepcopy(item)
    changed["pair"]["shadow"]["forecasts"][0]["model_over_probability"] = .99
    with pytest.raises(ValueError, match="changed"):
        series.aggregate([changed], now=AFTER)
    changed = copy.deepcopy(item)
    changed["market_archive"]["evidence"]["sources"]["kalshi"]["targets"]["team-1"][
        "details"]["abbreviation"] = "JAC"
    with pytest.raises(ValueError, match="integrity"):
        series.aggregate([changed], now=AFTER)
