"""Paired future-game model and venue benchmark audit."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from sportsbet.quant.kalshi_market_cohort import digest, freeze
from sportsbet.quant import kalshi_role_shadow as role
from sportsbet.quant import kalshi_role_shadow_v2 as role_v2
from sportsbet.quant import kalshi_role_shadow_eval as paired
from sportsbet.quant.kalshi_market_settlement import VERSION as SETTLEMENT_VERSION
from tests.test_kalshi_role_shadow import NOW, RULES, fixture
from tests.test_kalshi_role_shadow_v2 import manifest


AFTER = datetime(2026, 10, 5, tzinfo=timezone.utc)


def venue(cohort, result="no"):
    offer, = cohort["selections"]
    contract = dict(ticker=offer["ticker"],
        event_ticker=offer["ticker"].rsplit("-", 1)[0], status="finalized",
        result=result, settlement_value_dollars="1.0000" if result == "yes" else "0.0000",
        settlement_ts="2026-10-04T22:00:00+00:00", market_type="binary",
        notional_value_dollars="1.0000", strike_type="greater",
        floor_strike=float(offer["line"]),
        custom_strike=dict(football_player=offer["player_target_id"],
                           football_team=offer["team_target_id"]),
        rules_primary=RULES["primary"], rules_secondary=RULES["secondary"])
    evidence = dict(protocol=SETTLEMENT_VERSION,
        selection_sha256=cohort["selection_sha256"],
        pages=[dict(tickers=[offer["ticker"]],
                    request_started_at="2026-10-04T23:00:00+00:00",
                    received_at="2026-10-04T23:00:01+00:00",
                    body=dict(markets=[contract], cursor=""))])
    return dict(evidence=evidence, evidence_sha256=digest(evidence))


def test_paired_score_requires_same_verified_contract_and_keeps_no_edge_claim(monkeypatch):
    archive, cohort, stats, snaps, identity = fixture()
    shadow = role.predict(archive, cohort, stats, snaps, identity, now=NOW)
    monkeypatch.setattr(paired, "build_report", lambda *args, **kwargs: shadow)
    report = paired.evaluate(archive, cohort, shadow, Path("unused"), venue(cohort), now=AFTER)
    assert report["cohort_contracts"] == report["shadow_forecasts"] == 1
    assert report["paired_venue_verified"] == report["paired_verified_games"] == 1
    assert report["paired_result_counts"] == {"venue_verified": 1}
    assert float(report["paired_market_minus_model_brier"]) > 0
    assert float(report["paired_market_minus_model_log_loss"]) > 0
    assert report["minimum_50_independent_games_met"] is False
    assert report["roi"] is None and report["edge_established"] is False
    assert report["price_contemporaneous_with_model"] is False
    assert report["quote_pairs_within_5m"] == report["verified_pairs_within_5m"] == 0
    assert float(report["quote_age_seconds_min"]) > 300


def test_fresh_quote_is_counted_but_still_not_an_executable_offer(monkeypatch):
    archive, _, stats, snaps, identity = fixture()
    cohort = freeze(archive, "2026-10-02T18:44:00+00:00")
    generated = datetime(2026, 10, 2, 18, 46, tzinfo=timezone.utc)
    shadow = role.predict(archive, cohort, stats, snaps, identity, now=generated)
    monkeypatch.setattr(paired, "build_report", lambda *args, **kwargs: shadow)
    report = paired.evaluate(archive, cohort, shadow, Path("unused"), venue(cohort), now=AFTER)
    assert report["quote_pairs_within_5m"] == report["verified_pairs_within_5m"] == 1
    assert report["price_contemporaneous_with_model"] is True
    assert report["market_midpoint_executable"] is False
    assert report["edge_established"] is False


def test_forward_source_receipt_replays_before_venue_scoring(monkeypatch):
    archive, _, stats, snaps, identity = fixture()
    cohort = freeze(archive, "2026-10-02T18:44:00+00:00")
    generated = datetime(2026, 10, 2, 18, 46, tzinfo=timezone.utc)
    source = manifest()
    source["staged_at"] = "2026-10-02T18:43:00+00:00"
    for asset in source["assets"].values():
        asset["updated_at"] = "2026-10-02T18:42:00+00:00"
    for response in source["release_responses"].values():
        listing = json.loads(response["text"])
        for item in listing["assets"]:
            item["updated_at"] = "2026-10-02T18:42:00+00:00"
        response["text"] = json.dumps(listing)
        response["sha256"] = hashlib.sha256(response["text"].encode()).hexdigest()
    monkeypatch.setattr(role_v2, "load_sources", lambda *args: (stats, snaps))
    monkeypatch.setattr(role_v2.v1, "identity_index", lambda *args: identity)
    shadow = role_v2.build_report(archive, cohort, Path("unused"), source, now=generated)
    report = paired.evaluate(archive, cohort, shadow, Path("unused"), venue(cohort), now=AFTER)
    assert report["protocol"] == paired.FORWARD_VERSION
    assert report["paired_venue_verified"] == report["quote_pairs_within_5m"] == 1
    changed = copy.deepcopy(shadow)
    changed["source_manifest"]["assets"]["stats_2026"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="changed"):
        paired.evaluate(archive, cohort, changed, Path("unused"), venue(cohort), now=AFTER)


def test_model_receipt_cannot_precede_frozen_contract_selection(monkeypatch):
    archive, cohort, stats, snaps, identity = fixture()
    shadow = role.predict(archive, cohort, stats, snaps, identity,
                          now=datetime(2026, 10, 3, 7, 28, tzinfo=timezone.utc))
    monkeypatch.setattr(paired, "build_report", lambda *args, **kwargs: shadow)
    with pytest.raises(ValueError, match="changed"):
        paired.evaluate(archive, cohort, shadow, Path("unused"), venue(cohort), now=AFTER)


def test_unreturned_contract_keeps_model_and_market_pair_unscored(monkeypatch):
    archive, cohort, stats, snaps, identity = fixture()
    shadow = role.predict(archive, cohort, stats, snaps, identity, now=NOW)
    monkeypatch.setattr(paired, "build_report", lambda *args, **kwargs: shadow)
    settled = venue(cohort)
    settled["evidence"]["pages"][0]["body"]["markets"] = []
    settled["evidence_sha256"] = digest(settled["evidence"])
    report = paired.evaluate(archive, cohort, shadow, Path("unused"), settled, now=AFTER)
    assert report["shadow_forecasts"] == 1
    assert report["paired_venue_verified"] == 0
    assert report["paired_result_counts"] == {"not_returned": 1}
    assert report["model_verified_subset_brier"] is None
    assert report["model_verified_subset_log_loss"] is None
    assert report["complete"] is False


def test_changed_frozen_probability_or_future_response_is_rejected(monkeypatch):
    archive, cohort, stats, snaps, identity = fixture()
    shadow = role.predict(archive, cohort, stats, snaps, identity, now=NOW)
    monkeypatch.setattr(paired, "build_report", lambda *args, **kwargs: shadow)
    changed = copy.deepcopy(shadow)
    changed["forecasts"][0]["model_over_probability"] = 0.99
    with pytest.raises(ValueError, match="changed"):
        paired.evaluate(archive, cohort, changed, Path("unused"), venue(cohort), now=AFTER)
    with pytest.raises(ValueError, match="chronology"):
        paired.evaluate(archive, cohort, shadow, Path("unused"), venue(cohort),
                        now=datetime(2026, 10, 4, 22, tzinfo=timezone.utc))
