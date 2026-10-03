"""Pregame NFL role model and teammate-context safety boundaries."""
import copy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest

from sportsbet.quant.kalshi_market_cohort import freeze
from sportsbet.quant import kalshi_role_shadow as role
from sportsbet.quant.kalshi_role_shadow import predict


PLAYER = "00-0000001"
PFR = "Player01"
START = "2026-10-04T17:00:00+00:00"
NOW = datetime(2026, 10, 3, 8, 20, tzinfo=timezone.utc)
RULES = {"primary": "Four or more?", "secondary": "Venue participation terms."}


def fixture(prop="receptions", line="3.5"):
    quote = dict(ticker=f"KXNFLREC-26OCT04TEST-PLAYER-{int(Decimal(line)+Decimal('.5'))}",
        milestone_id="game-1", player_target_id="target-1", team_target_id="team-1",
        prop_type=prop, line=line,
        request_started_at="2026-10-02T18:43:20+00:00",
        received_at="2026-10-02T18:43:21+00:00", scheduled_game_start_time=START,
        market_sha256="a"*64,
        rules_sha256=hashlib.sha256(json.dumps(
            RULES, sort_keys=True, allow_nan=False).encode()).hexdigest(),
        source_page_sha256="c"*64,
        yes_ask={"cost": "0.52", "displayed_size": "10"},
        no_ask={"cost": "0.50", "displayed_size": "10"})
    evidence = dict(schema_version=2, sport="nfl", captured_at="2026-10-02T18:43:24+00:00",
        sources={"kalshi": dict(status="observed", partial_coverage=False,
            targets={"team-1": {"details": {"abbreviation": "PIT"}}},
            games=[{"milestone": {"id": "game-1", "start_date": START,
                                  "details": {"home_team_id": "team-1",
                                              "away_team_id": "team-2"}}}],
            prop_inventory=dict(partial_coverage=False,
                coverage=dict(discovery_complete=True, series_expected=4,
                              series_observed=4, structured_quote_markets=1),
                targets={"target-1": {"player_name": "Example Player",
                                      "team_target_id": "team-1"}}, quotes=[quote]))})
    archive = dict(evidence=evidence, summary=dict(sport="nfl", captured_at=evidence["captured_at"],
        evidence_sha256=hashlib.sha256(json.dumps(
            evidence, sort_keys=True, allow_nan=False).encode()).hexdigest()))
    stats, snaps = [], []
    for i in range(20):
        season, week = (2024, i+1) if i < 17 else (2026, i-16)
        value = 5 if i % 2 else 2
        stats.append(dict(player_id=PLAYER, team="PIT", season=season,
            week=week, season_type="REG", receptions=value, receiving_yards=value*10,
            rushing_yards=value*8, passing_yards=value*20,
            targets=4, carries=3, attempts=2))
        snaps.append(dict(pfr_player_id=PFR, team="PIT", season=season,
                          week=week, offense_snaps=10))
        if season == 2026:
            stats.append(dict(player_id="00-9999999", team="PIT", season=season,
                week=week, season_type="REG", receptions=6, receiving_yards=60,
                rushing_yards=30, passing_yards=0, targets=6, carries=7, attempts=0))
    return archive, freeze(archive, "2026-10-03T07:29:15+00:00"), stats, snaps, {
        "exampleplayer": {(PLAYER, PFR)}}


def run(data):
    return predict(*data, now=NOW)


def test_current_role_and_teammate_share_are_frozen_before_game():
    report = run(fixture())
    assert report["selected_contracts"] == report["forecast_contracts"] == 1
    row, = report["forecasts"]
    assert row["sample_games"] == 20 and row["current_team_games"] == 3
    assert row["older_games"] == 17
    assert row["teammate_context"]["recent_share"] == 0.4
    assert row["teammate_context"]["largest_teammate_share"] == 0.6
    assert row["model_over_probability"] > 0
    assert report["qualified_picks"] == 0 and report["edge_established"] is False
    assert report["model_forecasts_matched_to_live_price"] is False
    assert report["implementation_sha256"] == hashlib.sha256(
        Path(role.__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_offensive_snap_proves_zero_stat_game_but_missing_field_does_not():
    data = fixture()
    data[2].pop(0)
    report = run(data)
    assert report["forecasts"][0]["snap_backed_zero_games"] == 1
    data = fixture()
    data[2][0]["receptions"] = None
    assert run(data)["unavailable_reasons"] == {"missing_played_stat": 1}


def test_nonzero_stat_without_offensive_snap_and_insufficient_history_fail():
    data = fixture()
    data[3].pop(0)
    assert run(data)["unavailable_reasons"] == {"stat_without_offense_snap": 1}
    data = fixture()
    data[2].pop(0)
    data[3].pop(0)
    assert run(data)["unavailable_reasons"] == {"fewer_than_20_offensive_games": 1}


def test_other_offensive_usage_cannot_hide_a_played_game_from_prop_history():
    data = fixture()
    data[2][0]["receptions"] = 0
    data[3].pop(0)
    assert run(data)["unavailable_reasons"] == {"stat_without_offense_snap": 1}


def test_negative_rushing_yards_are_valid_played_stats():
    data = fixture(prop="rush_yds", line="0.5")
    data[2][0]["rushing_yards"] = -3
    assert run(data)["forecast_contracts"] == 1


def test_ambiguous_name_or_changed_recent_team_stays_unavailable():
    data = fixture()
    data[4]["exampleplayer"].add(("00-0000002", "Other01"))
    assert run(data)["unavailable_reasons"] == {"missing_or_ambiguous_identity": 1}
    data = fixture()
    data[3][-1]["team"] = "CLE"
    data[2][-2]["team"] = "CLE"  # last teammate row is unrelated; player stat stays PIT
    assert run(data)["unavailable_reasons"] == {"insufficient_current_team_role": 1}


def test_future_or_tampered_market_cannot_be_frozen():
    data = fixture()
    with pytest.raises(ValueError, match="before every selected game"):
        predict(*data, now=datetime(2026, 10, 4, 17, tzinfo=timezone.utc))
    changed = copy.deepcopy(data[1])
    changed["selections"][0]["line"] = "4.5"
    with pytest.raises(ValueError, match="selection"):
        predict(data[0], changed, data[2], data[3], data[4], now=NOW)
