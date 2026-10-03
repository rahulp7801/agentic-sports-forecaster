"""Fee-inclusive unit shadow must keep exact prices, events, and results."""
from __future__ import annotations

import copy
from datetime import timedelta
from decimal import Decimal
import hashlib
import json

import pytest

from sportsbet.quant import kalshi_ask_policy as ask
from sportsbet.quant import kalshi_prior20_ask_policy as prior
from sportsbet.quant import kalshi_fee_score as fees
from sportsbet.quant import kalshi_role_shadow_v2 as role
from sportsbet.quant.kalshi_market_cohort import digest, freeze
from tests.test_kalshi_pair_artifact import NOW
from tests.test_kalshi_role_shadow import fixture
from tests.test_kalshi_role_shadow_eval import AFTER, venue
from tests.test_kalshi_role_shadow_v2 import manifest


def setup_pair(monkeypatch: pytest.MonkeyPatch) -> tuple[dict, dict]:
    archive, _, stats, snaps, identity = fixture()
    quote = archive["evidence"]["sources"]["kalshi"]["prop_inventory"]["quotes"][0]
    event = quote["event_ticker"]
    archive["evidence"]["sources"]["kalshi"]["prop_inventory"]["fee_contexts"] = {
        event: dict(status="observed", event_ticker=event,
                    received_at=quote["received_at"],
                    series=dict(ticker=quote["series_ticker"],
                                last_updated_ts=quote["request_started_at"],
                                fee_type="quadratic", fee_multiplier="1"),
                    series_changes=dict(series_fee_change_arr=[]),
                    event_changes=dict(cursor="", event_fee_changes=[]))}
    archive["summary"]["evidence_sha256"] = hashlib.sha256(json.dumps(
        archive["evidence"], sort_keys=True, allow_nan=False).encode()).hexdigest()
    cohort = freeze(archive, NOW.isoformat())
    monkeypatch.setattr(role, "load_sources", lambda *args: (stats, snaps))
    monkeypatch.setattr(role.v1, "identity_index", lambda *args: identity)
    shadow = role.build_report(archive, cohort, None, manifest(), now=NOW)
    shadow["forecasts"][0]["model_over_probability"] = .8
    shadow["forecasts"][0]["prior20_over_probability"] = .8
    shadow["forecasts_sha256"] = digest(shadow["forecasts"])
    pair = dict(protocol="kalshi-nfl-contemporaneous-pair-v1",
                started_at=NOW.isoformat(),
                completed_at=(NOW+timedelta(seconds=2)).isoformat(),
                market_selection_sha256=cohort["selection_sha256"],
                forecasts_sha256=shadow["forecasts_sha256"],
                selected_contracts=1, forecast_contracts=1,
                cohort=cohort, shadow=shadow)
    pair["ask_policy"] = ask.freeze(pair, decided_at=NOW+timedelta(seconds=3))
    pair["prior20_ask_policy"] = prior.freeze(
        pair, decided_at=NOW+timedelta(seconds=3))
    monkeypatch.setattr(role, "build_report", lambda *args, **kwargs: pair["shadow"])
    return pair, archive


def test_preoutcome_fee_receipt_and_exact_yes_result(monkeypatch: pytest.MonkeyPatch):
    pair, archive = setup_pair(monkeypatch)
    pre, rows = fees.preoutcome(pair, archive)
    assert pre["candidates"] == pre["modeled_one_contract_costs"] == 1
    assert rows[0]["direct_total_cost"] == "0.5375"
    assert rows[0]["nondirect_total_cost"] == "0.54"
    assert pre["conditional_binary_direct_break_even_wins"] == 1
    assert pre["model_source_replayed"] is False
    prior_pre, _ = fees.preoutcome(pair, archive, policy="prior20")
    assert prior_pre["candidates"] == 1
    assert prior_pre["all_candidates_direct_cost"] == "0.5375"
    report = fees.evaluate(pair, archive, None, venue(pair["cohort"], "yes"), now=AFTER)
    assert report["candidate_result_counts"] == {"venue_verified": 1}
    assert report["full_cohort_hypothetical_direct_unit_profit"] == "0.4625"
    assert report["complete_binary_results"] is True
    assert report["model_source_replayed"] is True
    assert report["verified_subset_equal_game_direct_unit_profit_per_candidate"] == "0.4625"
    assert report["verified_subset_equal_game_direct_game_cluster_95"] is None
    prior_report = fees.evaluate(pair, archive, None, venue(pair["cohort"], "yes"),
                                 policy="prior20", now=AFTER)
    assert prior_report["full_cohort_hypothetical_direct_unit_profit"] == "0.4625"
    assert report["roi"] is None and report["edge_established"] is False
    assert report["actual_fills_verified"] is False


@pytest.mark.parametrize("kind", ["missing", "nonbinary", "wrong_event"])
def test_unavailable_result_is_not_imputed_as_loss(monkeypatch: pytest.MonkeyPatch, kind: str):
    pair, archive = setup_pair(monkeypatch)
    result = venue(pair["cohort"], "no")
    contract = result["evidence"]["pages"][0]["body"]["markets"][0]
    if kind == "missing":
        result["evidence"]["pages"][0]["body"]["markets"] = []
    elif kind == "nonbinary":
        contract["result"] = "void"
    else:
        contract["event_ticker"] = "KXNFLREC-26OCT04OTHER"
    result["evidence_sha256"] = digest(result["evidence"])
    report = fees.evaluate(pair, archive, None, result, now=AFTER)
    assert report["candidates"] == 1
    assert report["verified_binary_candidates"] == 0
    assert report["full_cohort_hypothetical_direct_unit_profit"] is None
    assert report["complete_binary_results"] is False
    assert report["verified_subset_hypothetical_direct_unit_profit"] is None


def test_tampered_fee_source_or_candidate_fails(monkeypatch: pytest.MonkeyPatch):
    pair, archive = setup_pair(monkeypatch)
    changed = copy.deepcopy(archive)
    event = next(iter(changed["evidence"]["sources"]["kalshi"]["prop_inventory"]["fee_contexts"]))
    changed["evidence"]["sources"]["kalshi"]["prop_inventory"]["fee_contexts"][event]["series"]["fee_multiplier"] = "0"
    with pytest.raises(ValueError, match="integrity|commitment"):
        fees.preoutcome(pair, changed)
    changed_pair = copy.deepcopy(pair)
    changed_pair["ask_policy"]["candidates"][0]["displayed_ask"] = "0.01"
    with pytest.raises(ValueError, match="receipt changed"):
        fees.preoutcome(changed_pair, archive)
