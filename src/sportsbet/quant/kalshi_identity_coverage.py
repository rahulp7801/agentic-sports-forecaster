"""Offline NFL Kalshi quote-to-history coverage diagnostic; never produces picks."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import unicodedata

STAT_FIELD = {
    "pass_yds": "passing_yards",
    "rush_yds": "rushing_yards",
    "rec_yds": "receiving_yards",
    "receptions": "receptions",
}


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return result


def _name(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing player name")
    ascii_name = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    result = re.sub(r"[^a-z0-9]", "", ascii_name.casefold())
    if not result:
        raise ValueError("Invalid player name")
    return result


def _market(archive: dict) -> tuple[dict, datetime]:
    evidence, summary = archive["evidence"], archive["summary"]
    encoded = json.dumps(evidence, sort_keys=True, allow_nan=False).encode()
    if (hashlib.sha256(encoded).hexdigest() != summary.get("evidence_sha256")
            or evidence.get("schema_version") != 2
            or evidence.get("sport") != "nfl"
            or summary.get("sport") != "nfl"
            or summary.get("captured_at") != evidence.get("captured_at")):
        raise ValueError("Market archive integrity or scope failed")
    capture = _time(evidence["captured_at"])
    source = evidence["sources"]["kalshi"]
    inventory = source["prop_inventory"]
    coverage = inventory["coverage"]
    if (source.get("status") != "observed"
            or source.get("partial_coverage") is not False
            or inventory.get("partial_coverage") is not False
            or coverage.get("discovery_complete") is not True
            or coverage.get("series_observed") != coverage.get("series_expected")
            or coverage.get("structured_quote_markets") != len(inventory["quotes"])):
        raise ValueError("Kalshi capture is incomplete")
    return source, capture


def audit(archive: dict, snapshot: dict) -> dict:
    source, capture = _market(archive)
    if _time(snapshot["observed_at"]) > capture:
        raise ValueError("History snapshot was captured after market quotes")
    inventory = source["prop_inventory"]
    quotes = inventory["quotes"]
    player_targets = inventory["targets"]
    team_targets = source["targets"]
    quoted_games = {quote["milestone_id"] for quote in quotes}
    games = {game["milestone"]["id"]: game["milestone"] for game in source["games"]}
    if len(games) != len(source["games"]) or not quoted_games <= set(games):
        raise ValueError("Quoted game identity is missing or ambiguous")
    game_seasons = {games[game_id]["details"]["season"]["year"] for game_id in quoted_games}
    if len(game_seasons) != 1 or any(type(year) is not int for year in game_seasons):
        raise ValueError("Quoted games need one captured NFL season")
    season = next(iter(game_seasons))
    if not isinstance(snapshot.get("nfl_base"), list) or not isinstance(snapshot.get("nfl_games"), list):
        raise ValueError("Missing NFL source rows or schedule")
    game_dates: dict[tuple[int, int, str], date] = {}
    for game in snapshot["nfl_games"]:
        game_date = date.fromisoformat(game["game_date"])
        for team in (game["home_team"], game["away_team"]):
            key = (game["season"], game["week"], team)
            if key in game_dates:
                raise ValueError("Ambiguous NFL game chronology")
            game_dates[key] = game_date

    # Historical rows are a necessary sample check, not a current-roster proof.
    source_rows: dict[str, list[dict]] = defaultdict(list)
    current_ids: dict[tuple[str, str], set[str]] = defaultdict(set)
    skipped_late = 0
    skipped_game_date = 0
    for row in snapshot["nfl_base"]:
        if _time(row["source_observed_at"]) > capture:
            skipped_late += 1
            continue
        game_date = game_dates.get((row["season"], row["week"], row["team"]))
        if game_date is None or game_date >= capture.date():
            skipped_game_date += 1
            continue
        player_id = row["player_id"]
        team = row["team"]
        if not isinstance(player_id, str) or not player_id or not isinstance(team, str) or not team:
            raise ValueError("Invalid history identity")
        source_rows[player_id].append(row)
        if row["season"] == season:
            current_ids[(_name(row["player_name"]), team)].add(player_id)

    target_state: dict[str, tuple[str, str | None]] = {}
    for quote in quotes:
        if quote["prop_type"] not in STAT_FIELD:
            raise ValueError("Unsupported quote market")
        player_target = player_targets[quote["player_target_id"]]
        team_target = team_targets[quote["team_target_id"]]
        milestone = games[quote["milestone_id"]]
        if (player_target["team_target_id"] != quote["team_target_id"]
                or quote["team_target_id"] not in (
                    milestone["details"]["home_team_id"], milestone["details"]["away_team_id"])
                or _time(quote["scheduled_game_start_time"]) != _time(milestone["start_date"])
                or _time(quote["received_at"]) > capture
                or _time(quote["scheduled_game_start_time"]) <= capture
                or Decimal(str(quote["line"])) % 1 != Decimal(".5")):
            raise ValueError("Quote chronology or target mismatch")
        target_id = quote["player_target_id"]
        team = team_target["details"]["abbreviation"]
        matches = current_ids[(_name(player_target["player_name"]), team)]
        state = ("unique_name_team" if len(matches) == 1 else
                 "ambiguous_name_team" if matches else "no_name_team_match")
        player_id = next(iter(matches)) if len(matches) == 1 else None
        previous = target_state.setdefault(target_id, (state, player_id))
        if previous != (state, player_id):
            raise ValueError("Player target changed identity within capture")

    targets = Counter(state for state, _ in target_state.values())
    line_counts: Counter[str] = Counter()
    pair_state: dict[tuple[str, str, str], str] = {}
    for quote in quotes:
        state, player_id = target_state[quote["player_target_id"]]
        if player_id is None:
            line_counts[state] += 1
            continue
        field = STAT_FIELD[quote["prop_type"]]
        team = team_targets[quote["team_target_id"]]["details"]["abbreviation"]
        rows = [r for r in source_rows[player_id] if r.get(field) is not None]
        # A duplicate season/week could count one actual game twice.
        game_keys = {(r["season"], r["week"]) for r in rows}
        if len(game_keys) != len(rows):
            state = "duplicate_history_game"
        else:
            current = sum(r["season"] == season and r["team"] == team for r in rows)
            older = sum(r["season"] < season for r in rows)
            state = ("necessary_history_present" if len(rows) >= 20 and current >= 2 and older >= 1
                     else "fewer_than_20_stats" if len(rows) < 20
                     else "fewer_than_2_current_team_stats" if current < 2
                     else "no_older_stats")
        line_counts[state] += 1
        pair_key = (player_id, quote["milestone_id"], quote["prop_type"])
        previous = pair_state.setdefault(pair_key, state)
        if previous != state:
            raise ValueError("Player/game/market coverage changed within capture")

    return {
        "version": "kalshi-nfl-identity-coverage-v1",
        "capture_at": capture.isoformat(),
        "market_archive_sha256": hashlib.sha256(
            json.dumps(archive["evidence"], sort_keys=True, allow_nan=False).encode()
        ).hexdigest(),
        "target_counts": dict(sorted(targets.items())),
        "quote_line_counts": dict(sorted(line_counts.items())),
        "unique_player_game_market_counts": dict(sorted(Counter(pair_state.values()).items())),
        "source_rows_after_capture_skipped": skipped_late,
        "source_rows_without_past_game_skipped": skipped_game_date,
        "settlement_equivalent_quotes": sum(q["settlement_equivalent"] is True for q in quotes),
        "execution_ready_quotes": sum(q["execution_ready"] is True for q in quotes),
        "limitations": [
            "Exact name and captured team intersect historical rows; current roster is unverified.",
            "Source row presence is necessary, not proof of complete participation or a model estimate.",
            "No Kalshi contract settlement or matched-price returns were evaluated.",
        ],
        "target_verified": False,
        "promote": False,
        "execution_ready": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-archive", type=Path, required=True)
    parser.add_argument("--history-snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(json.loads(args.market_archive.read_text(encoding="utf-8")),
                   json.loads(args.history_snapshot.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print("Offline Kalshi identity coverage audit completed")


if __name__ == "__main__":
    main()
