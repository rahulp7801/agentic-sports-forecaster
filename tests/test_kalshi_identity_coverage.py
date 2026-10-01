"""Meaningful boundaries for the offline free-quote feasibility diagnostic."""
import copy
import hashlib
import json

import pytest

from sportsbet.quant.kalshi_identity_coverage import audit

CAPTURE = "2026-12-30T12:00:00+00:00"
START = "2027-01-03T18:00:00+00:00"


def fixture():
    quote = {
        "player_target_id": "player-1",
        "team_target_id": "team-1",
        "milestone_id": "game-1",
        "prop_type": "rec_yds",
        "line": "40.5",
        "received_at": CAPTURE,
        "scheduled_game_start_time": START,
        "settlement_equivalent": False,
        "execution_ready": False,
    }
    evidence = {
        "schema_version": 2,
        "sport": "nfl",
        "captured_at": CAPTURE,
        "sources": {
            "kalshi": {
                "status": "observed",
                "partial_coverage": False,
                "targets": {"team-1": {"details": {"abbreviation": "KC"}}},
                "games": [{"milestone": {"id": "game-1", "start_date": START,
                                         "details": {"season": {"year": 2026},
                                                     "home_team_id": "team-1",
                                                     "away_team_id": "team-2"}}}],
                "prop_inventory": {
                    "partial_coverage": False,
                    "coverage": {"discovery_complete": True, "series_observed": 1,
                                 "series_expected": 1, "structured_quote_markets": 1},
                    "targets": {"player-1": {"player_name": "Example Player",
                                             "team_target_id": "team-1"}},
                    "quotes": [quote],
                },
            },
        },
    }
    archive = {
        "evidence": evidence,
        "summary": {
            "sport": "nfl",
            "captured_at": CAPTURE,
            "evidence_sha256": hashlib.sha256(
                json.dumps(evidence, sort_keys=True, allow_nan=False).encode()
            ).hexdigest(),
        },
    }
    rows = [
        {
            "source_observed_at": "2026-12-29T00:00:00+00:00",
            "player_id": "00-0000001",
            "player_name": "Example Player",
            "team": "KC",
            "season": 2025 if week <= 18 else 2026,
            "week": week if week <= 18 else week - 18,
            "receiving_yards": 50,
        }
        for week in range(1, 21)
    ]
    games = [{"season": row["season"], "week": row["week"],
              "home_team": "KC", "away_team": "DEN",
              "game_date": f'{row["season"]}-09-{row["week"]:02d}'} for row in rows]
    return archive, {"observed_at": "2026-12-29T12:00:00+00:00",
                     "nfl_base": rows, "nfl_games": games}


def test_january_game_uses_captured_nfl_season_and_preserves_nonpromotion():
    archive, history = fixture()
    result = audit(archive, history)
    assert result["target_counts"] == {"unique_name_team": 1}
    assert result["unique_player_game_market_counts"] == {"necessary_history_present": 1}
    assert result["quote_line_counts"] == {"necessary_history_present": 1}
    assert result["settlement_equivalent_quotes"] == 0
    assert result["target_verified"] is False
    assert result["promote"] is False


def test_archive_tampering_and_late_source_rows_fail_closed():
    archive, history = fixture()
    corrupted = copy.deepcopy(archive)
    corrupted["evidence"]["sources"]["kalshi"]["prop_inventory"]["quotes"][0]["line"] = "41.5"
    with pytest.raises(ValueError, match="integrity"):
        audit(corrupted, history)

    history["nfl_base"][-1]["source_observed_at"] = "2026-12-31T00:00:00+00:00"
    result = audit(archive, history)
    assert result["source_rows_after_capture_skipped"] == 1
    assert result["unique_player_game_market_counts"] == {"fewer_than_20_stats": 1}


def test_future_or_unlinked_game_cannot_supply_a_stat():
    archive, history = fixture()
    history["nfl_games"][-1]["game_date"] = "2027-01-01"
    result = audit(archive, history)
    assert result["source_rows_without_past_game_skipped"] == 1
    assert result["unique_player_game_market_counts"] == {"fewer_than_20_stats": 1}


def test_history_snapshot_after_quote_is_rejected():
    archive, history = fixture()
    history["observed_at"] = "2026-12-31T00:00:00+00:00"
    with pytest.raises(ValueError, match="after market quotes"):
        audit(archive, history)


def test_quote_team_must_belong_to_captured_game():
    archive, history = fixture()
    archive["evidence"]["sources"]["kalshi"]["games"][0]["milestone"]["details"]["home_team_id"] = "other"
    archive["summary"]["evidence_sha256"] = hashlib.sha256(
        json.dumps(archive["evidence"], sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="target mismatch"):
        audit(archive, history)
