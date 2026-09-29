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


def test_price_control_does_not_require_earlier_side_to_have_own_baseline():
    a,b,c = pair(); b["q"] = None; b["entry"] -= timedelta(microseconds=20)
    assert controls.compare([c],[a,b])["matched_prices"] == 1


def test_price_control_reproduces_selected_market_probability():
    a,b,c = pair(); b["q"] = None; b["row"]["american_odds"] = 150
    assert controls.compare([c],[a,b])["excluded"] == {"conflicting_market_baseline": 1}


def test_source_price_observations_keep_first_side_and_reject_bad_proof():
    from tests.test_market_challengers import payload
    a = payload(prediction_id="first")
    for field in list(a):
        if field.startswith("market_"): a.pop(field)
    observed = controls.price_observations([a], "nfl", "empirical-jeffreys-v4")
    assert len(observed) == 1 and observed[0]["q"] is None
    assert search.frozen.observations([a], "nfl", "empirical-jeffreys-v4")[0] == []
    a["quote_source_record_sha256"] = "0"*64
    assert controls.price_observations([a], "nfl", "empirical-jeffreys-v4") == []


def embedded_pair():
    from tests.test_scan_market_baseline import quotes
    from sportsbet.quant.market_baseline import paired_market_baseline
    over, under = quotes()
    a = item(side="over", odds=-110, p=.8, q=.5, y=1,
             entry=over.snapped_at+timedelta(seconds=1), quote=over.snapped_at,
             start=over.game_start_time)
    a["row"].update(sport=over.sport, game_id=over.game_id, player=over.player_name,
                    prop_type="receptions", line=float(over.line), sportsbook=over.sportsbook,
                    quote_time=over.snapped_at.isoformat(),
                    game_start_time=over.game_start_time.isoformat(),
                    quote_source_provider=over.source_provider,
                    quote_source_sha256=over.source_sha256,
                    **paired_market_baseline(over,[over,under]))
    c=dict(x=a, probability=.8, profit=100/110, decision=a["entry"], ev=.5)
    return a,c


def test_embedded_verified_opposite_can_supply_price_without_second_forecast():
    a,c=embedded_pair()
    r=controls.compare([c],[])
    assert r["matched_prices"] == 1 and r["model_return"]["decisions"] == 1
    assert r["records"][0]["opposite_evidence_origin"] == "embedded_verified_opposite"
    assert r["controls"]["always_under"]["return"]["mean"] == -1
    a["y"]=None
    assert controls.compare([c],[])["excluded"] == {"pending_pair":1}


def test_embedded_opposite_cannot_use_tampered_price_or_hash():
    a,c=embedded_pair(); a["row"]["market_opposite_american_odds"]=-105
    assert controls.compare([c],[])["matched_prices"] == 0
    a,c=embedded_pair(); a["row"]["market_opposite_quote_source_record_sha256"]="0"*64
    assert controls.compare([c],[])["matched_prices"] == 0


def test_embedded_opposite_conflict_with_separate_receipt_is_rejected():
    a,c=embedded_pair(); b=deepcopy(a)
    b["row"]["direction"]="under"; b["row"]["american_odds"]=-105
    assert controls.compare([c],[b])["excluded"] == {"conflicting_opposite_prices":1}
