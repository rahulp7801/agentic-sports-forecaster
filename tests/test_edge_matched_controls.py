from copy import deepcopy
from datetime import timedelta
import pytest
from sportsbet.quant import edge_matched_controls as controls
from sportsbet.quant import edge_search_stress as search
from tests.test_market_challengers import item, NOW


def pair():
    a = item(side="under", p=.2, q=.5, odds=-110, y=0)
    b = item(side="over", p=.2, q=.5, odds=-110, y=0)
    c = dict(x=a, probability=.8, profit=100/110, decision=NOW, ev=.8*(1+100/110)-1)
    return a, b, c


def test_matched_arithmetic_uses_one_unit_total_exposure():
    a, b, c = pair()
    r = controls.compare([c], [a,b])
    assert r["model_return"]["mean"] == pytest.approx(100/110)
    assert r["controls"]["always_under"]["paired_model_minus_control"]["mean"] == 0
    assert r["controls"]["always_over"]["return"]["mean"] == -1
    assert r["controls"]["half_each_side"]["return"]["mean"] == pytest.approx(-.04545454545)
    assert r["market_expected_return"]["mean"] == pytest.approx(-.04545454545)
    assert r["model_return"]["game_cluster_95"] is None


@pytest.mark.parametrize("change", ["later", "stale", "different_book", "different_line", "different_response"])
def test_opposite_requires_exact_available_fresh_quote(change):
    a, b, c = pair()
    if change == "later": b["entry"] = NOW+timedelta(seconds=1)
    if change == "stale": b["quote"] = NOW-timedelta(seconds=301)
    if change == "different_book": b["row"]["sportsbook"] = "other"
    if change == "different_line": b["unit"] = b["unit"][:3]+(9.5,)
    if change == "different_response": b["row"]["quote_source_sha256"] = "other"
    assert controls.compare([c], [a,b])["matched_prices"] == 0


def test_label_changes_do_not_change_matched_quote_eligibility():
    a, b, c = pair()
    original = controls.compare([c], [a,b])
    a["y"] = b["y"] = 1
    changed = controls.compare([c], [a,b])
    assert original["matched_ids"] == changed["matched_ids"]
    assert changed["model_return"]["mean"] == -1
    b["y"] = None
    pending = controls.compare([c], [a,b])
    assert pending["matched_ids"] == original["matched_ids"]
    assert pending["model_return"]["decisions"] == 0
    assert pending["excluded"] == {"pending_pair": 1}


def test_conflicting_verified_outcomes_are_not_silently_relabelled():
    a, b, c = pair(); b["y"] = 1
    r = controls.compare([c], [a,b])
    assert r["excluded"] == {"conflicting_verified_outcomes": 1}
    assert r["matched_prices"] == 1 and r["model_return"]["decisions"] == 0


def test_conflicting_prices_or_baselines_reject_pair():
    a, b, c = pair(); duplicate = deepcopy(b)
    duplicate["row"]["american_odds"] = 100
    assert controls.compare([c], [a,b,duplicate])["excluded"] == {"conflicting_opposite_prices": 1}
    b["q"] = .6
    assert controls.compare([c], [a,b])["excluded"] == {"conflicting_market_baseline": 1}


def test_other_game_player_cannot_supply_opposite():
    a,b,c = pair(); b["unit"] = ("other",)+b["unit"][1:]
    assert controls.compare([c], [a,b])["matched_prices"] == 0


def test_direction_scores_are_conditioned_on_selected_side():
    a,b,c = pair()
    r=controls.compare([c],[a,b])["calibration_by_selected_direction"]
    assert r["under"]["won"] == 1
    assert r["under"]["predicted_probability"] == .8
    assert r["over"]["decisions"] == 0
