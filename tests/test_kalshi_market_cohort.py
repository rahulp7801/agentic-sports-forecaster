"""Pregame, outcome-blind market baseline boundaries."""
import copy
import hashlib
import json

import pytest

from sportsbet.quant.kalshi_market_cohort import freeze


CAPTURE = "2026-10-02T18:43:24+00:00"
FROZEN = "2026-10-03T07:29:15+00:00"
START = "2026-10-04T17:00:00+00:00"
HASH = "a" * 64


def fixture():
    quote = {
        "ticker": "KXNFLREC-ONE-4", "milestone_id": "game-1",
        "player_target_id": "player-1", "team_target_id": "team-1",
        "prop_type": "receptions", "line": "3.5",
        "request_started_at": "2026-10-02T18:43:20+00:00",
        "received_at": "2026-10-02T18:43:21+00:00",
        "scheduled_game_start_time": START,
        "market_sha256": HASH, "rules_sha256": HASH,
        "source_page_sha256": HASH,
        "yes_ask": {"cost": "0.53", "displayed_size": "10"},
        "no_ask": {"cost": "0.49", "displayed_size": "8"},
        "settlement_equivalent": False, "execution_ready": False,
    }
    evidence = {
        "schema_version": 2, "sport": "nfl", "captured_at": CAPTURE,
        "sources": {"kalshi": {
            "status": "observed", "partial_coverage": False,
            "targets": {"team-1": {"details": {"abbreviation": "PIT"}}},
            "games": [{"milestone": {"id": "game-1", "start_date": START,
                                    "details": {"home_team_id": "team-1",
                                                "away_team_id": "team-2"}}}],
            "prop_inventory": {
                "partial_coverage": False,
                "coverage": {"discovery_complete": True, "series_expected": 4,
                             "series_observed": 4, "structured_quote_markets": 1},
                "targets": {"player-1": {"player_name": "Example Player",
                                         "team_target_id": "team-1"}},
                "quotes": [quote],
            },
        }},
    }
    archive = {"evidence": evidence, "summary": {"sport": "nfl", "captured_at": CAPTURE}}
    resign(archive)
    return archive


def resign(archive):
    archive["summary"]["evidence_sha256"] = hashlib.sha256(
        json.dumps(archive["evidence"], sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def test_freeze_selects_one_balanced_line_with_exact_source_commitment():
    archive = fixture()
    second = copy.deepcopy(archive["evidence"]["sources"]["kalshi"]["prop_inventory"]["quotes"][0])
    second.update(ticker="KXNFLREC-ONE-5", line="4.5",
                  yes_ask={"cost": "0.75", "displayed_size": "10"},
                  no_ask={"cost": "0.26", "displayed_size": "10"})
    one_sided = copy.deepcopy(second)
    one_sided.update(ticker="KXNFLREC-ONE-6", line="5.5", no_ask=None)
    inventory = archive["evidence"]["sources"]["kalshi"]["prop_inventory"]
    inventory["quotes"] = [one_sided, second, inventory["quotes"][0]]
    inventory["coverage"]["structured_quote_markets"] = 3
    resign(archive)
    result = freeze(archive, FROZEN)
    assert result["selected_contracts"] == 1
    assert result["selections"][0]["ticker"] == "KXNFLREC-ONE-4"
    assert result["excluded_quote_lines"] == {"one_sided_or_unquoted": 1}
    assert result["selections"][0]["settlement_equivalent"] is False
    assert result["edge_established"] is False
    reversed_archive = copy.deepcopy(archive)
    reversed_archive["evidence"]["sources"]["kalshi"]["prop_inventory"]["quotes"].reverse()
    resign(reversed_archive)
    assert freeze(reversed_archive, FROZEN)["selection_sha256"] == result["selection_sha256"]


def test_integrity_scope_and_incomplete_discovery_fail_closed():
    archive = fixture()
    archive["evidence"]["sources"]["kalshi"]["prop_inventory"]["quotes"][0]["line"] = "4.5"
    with pytest.raises(ValueError, match="integrity"):
        freeze(archive, FROZEN)
    resign(archive)
    archive["evidence"]["sources"]["kalshi"]["prop_inventory"]["coverage"]["discovery_complete"] = False
    resign(archive)
    with pytest.raises(ValueError, match="incomplete"):
        freeze(archive, FROZEN)


@pytest.mark.parametrize("change,reason", [
    ({"request_started_at": "2026-10-02T18:43:22+00:00"}, "chronology"),
    ({"team_target_id": "team-2"}, "identity"),
    ({"line": "3.4"}, "line"),
    ({"line": "-0.5"}, "line"),
    ({"request_started_at": "2026-10-02T18:00:00+00:00",
      "received_at": "2026-10-02T18:00:01+00:00"}, "chronology"),
    ({"source_page_sha256": "unknown"}, "commitment"),
    ({"yes_ask": {"cost": "0.01", "displayed_size": "1"},
      "no_ask": {"cost": "0.01", "displayed_size": "1"}}, "Crossed"),
])
def test_bad_source_quote_fails_closed(change, reason):
    archive = fixture()
    archive["evidence"]["sources"]["kalshi"]["prop_inventory"]["quotes"][0].update(change)
    resign(archive)
    with pytest.raises(ValueError, match=reason):
        freeze(archive, FROZEN)


def test_after_kickoff_is_not_selected_and_duplicate_ticker_is_rejected():
    archive = fixture()
    result = freeze(archive, "2026-10-04T17:00:00+00:00")
    assert result["selected_contracts"] == 0
    assert result["excluded_quote_lines"] == {"already_started_at_freeze": 1}
    inventory = archive["evidence"]["sources"]["kalshi"]["prop_inventory"]
    inventory["quotes"].append(copy.deepcopy(inventory["quotes"][0]))
    inventory["coverage"]["structured_quote_markets"] = 2
    resign(archive)
    with pytest.raises(ValueError, match="duplicate"):
        freeze(archive, FROZEN)


def test_freeze_cannot_predate_capture():
    with pytest.raises(ValueError, match="cannot precede"):
        freeze(fixture(), "2026-10-01T00:00:00+00:00")
