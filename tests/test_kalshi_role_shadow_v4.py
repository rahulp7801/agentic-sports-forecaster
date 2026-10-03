"""Jacksonville alias coverage is versioned and historic receipts remain replayable."""
import copy
import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest

from sportsbet.quant import kalshi_role_shadow as v1
from sportsbet.quant import kalshi_role_shadow_v2 as v3
from sportsbet.quant import kalshi_role_shadow_v4 as v4
from tests.test_kalshi_role_shadow import NOW, fixture
from tests.test_kalshi_role_shadow_v2 import manifest


def jacksonville():
    archive, cohort, stats, snaps, identity = fixture()
    archive["evidence"]["sources"]["kalshi"]["targets"]["team-1"]["details"]["abbreviation"] = "JAC"
    for row in stats + snaps:
        if row["team"] == "PIT":
            row["team"] = "JAX"
    # Re-freeze after changing quote evidence, including its hash.
    from sportsbet.quant.kalshi_market_cohort import freeze
    archive["summary"]["evidence_sha256"] = hashlib.sha256(json.dumps(
        archive["evidence"], sort_keys=True, allow_nan=False).encode()).hexdigest()
    cohort = freeze(archive, cohort["frozen_at"])
    return archive, cohort, stats, snaps, identity


def test_jac_quote_matches_jax_source_only_in_new_version():
    data = jacksonville()
    before = copy.deepcopy(data)
    old = v1.predict(*data, now=NOW)
    new = v4.predict(*data, now=NOW)
    assert old["forecast_contracts"] == 0
    assert old["unavailable_reasons"] == {"insufficient_current_team_role": 1}
    assert new["forecast_contracts"] == 1
    assert new["forecasts"][0]["current_team_games"] == 3
    assert new["team_alias_version"] == v4.TEAM_ALIAS_VERSION
    assert new["qualified_picks"] == 0 and new["edge_established"] is False
    assert data == before


def test_unrelated_team_forecast_is_unchanged_and_unselected_alias_ignored():
    data = fixture()
    old = v1.predict(*data, now=NOW)
    new = v4.predict(*data, now=NOW)
    assert new["forecasts"] == old["forecasts"]
    data = jacksonville()
    data[0]["evidence"]["sources"]["kalshi"]["targets"]["team-2"] = {
        "details": {"abbreviation": "JAX"}}
    archive = data[0]
    archive["summary"]["evidence_sha256"] = hashlib.sha256(json.dumps(
        archive["evidence"], sort_keys=True, allow_nan=False).encode()).hexdigest()
    from sportsbet.quant.kalshi_market_cohort import freeze
    data = (archive, freeze(archive, data[1]["frozen_at"]), *data[2:])
    assert v4.predict(*data, now=NOW)["forecast_contracts"] == 1


def test_new_manifest_receipt_has_prior20_and_old_builder_is_unchanged(monkeypatch, tmp_path):
    data = jacksonville()
    source = manifest()
    monkeypatch.setattr(v3, "load_sources", lambda *args: (data[2], data[3]))
    monkeypatch.setattr(v1, "identity_index", lambda *args: data[4])
    old = v3.build_report(data[0], data[1], tmp_path, source, now=NOW)
    new = v4.build_report(data[0], data[1], tmp_path, source, now=NOW)
    assert old["forecast_contracts"] == 0
    assert new["forecast_contracts"] == 1
    assert 0 < new["forecasts"][0]["prior20_over_probability"] < 1
    assert new == v4.build_report(data[0], data[1], tmp_path, source, now=NOW)
    assert new["implementation_sha256"] != old["implementation_sha256"]



def test_forward_pair_routes_through_v4_and_policies_accept_it(monkeypatch):
    from sportsbet.quant import kalshi_pair_capture as capture
    from sportsbet.quant.kalshi_market_cohort import digest
    from sportsbet.quant import kalshi_ask_policy as ask
    from sportsbet.quant import kalshi_prior20_ask_policy as prior
    from tests.test_kalshi_pair_capture import FRESH

    archive, _, stats, snaps, identity = fixture()
    source_manifest = {"test": "forward"}
    called = []
    def builder(market, cohort, source_dir, manifest, *, now):
        called.append(manifest)
        report = v4.predict(market, cohort, stats, snaps, identity, now=now)
        report["forecasts"][0]["prior20_over_probability"] = .5
        report["forecasts_sha256"] = digest(report["forecasts"])
        return report
    monkeypatch.setattr(capture.kalshi_role_shadow_v4, "build_report", builder)
    pair = capture.capture(archive, Path("unused"),
                           started_at=FRESH,
                           completed_at=FRESH + timedelta(seconds=2),
                           source_manifest=source_manifest)
    assert called == [source_manifest]
    assert pair["shadow"]["protocol"] == v4.VERSION
    assert ask.freeze(pair, decided_at=FRESH + timedelta(seconds=3))["model_forecasts"] == 1
    assert prior.freeze(pair, decided_at=FRESH + timedelta(seconds=3))["model_forecasts"] == 1


def test_private_artifact_packs_new_receipt_and_old_receipt(monkeypatch, tmp_path):
    from sportsbet.quant import kalshi_pair_artifact as artifact
    from sportsbet.quant.kalshi_ask_policy import freeze as freeze_ask
    from sportsbet.quant.kalshi_prior20_ask_policy import freeze as freeze_prior
    from tests.test_kalshi_pair_artifact import NOW as PAIR_NOW, setup

    pair_path, source_dir, market_dir = setup(tmp_path, monkeypatch)
    artifact.pack(pair_path, source_dir, market_dir, tmp_path / "old.zip")
    pair = json.loads(pair_path.read_text(encoding="utf-8"))
    archive = json.loads((market_dir / "market.json").read_text(encoding="utf-8"))
    source = pair["shadow"]["source_manifest"]
    pair["shadow"] = v4.build_report(archive, pair["cohort"], source_dir,
                                      source, now=PAIR_NOW)
    pair["forecasts_sha256"] = pair["shadow"]["forecasts_sha256"]
    pair["ask_policy"] = freeze_ask(pair, decided_at=PAIR_NOW + timedelta(seconds=3))
    pair["prior20_ask_policy"] = freeze_prior(
        pair, decided_at=PAIR_NOW + timedelta(seconds=3))
    pair_path.write_text(json.dumps(pair), encoding="utf-8")
    assert artifact.pack(pair_path, source_dir, market_dir,
                         tmp_path / "new.zip")["forecasts_sha256"] == pair["forecasts_sha256"]



def test_new_evaluation_version_replays_new_shadow_without_edge(monkeypatch):
    from sportsbet.quant import kalshi_role_shadow_eval as paired
    from sportsbet.quant.kalshi_market_cohort import digest
    from tests.test_kalshi_role_shadow_eval import AFTER, venue

    archive, cohort, stats, snaps, identity = fixture()
    shadow = v4.predict(archive, cohort, stats, snaps, identity, now=NOW)
    shadow["source_manifest"] = {}
    shadow["forecasts"][0]["prior20_over_probability"] = .5
    shadow["forecasts_sha256"] = digest(shadow["forecasts"])
    monkeypatch.setattr(paired.kalshi_role_shadow_v4, "build_report",
                        lambda *args, **kwargs: shadow)
    report = paired.evaluate(archive, cohort, shadow, Path("unused"),
                             venue(cohort), now=AFTER)
    assert report["protocol"] == paired.FORWARD_ALIAS_VERSION
    assert report["paired_venue_verified"] == 1
    assert report["minimum_50_independent_games_met"] is False
    assert report["qualified_picks"] == 0 and report["edge_established"] is False
