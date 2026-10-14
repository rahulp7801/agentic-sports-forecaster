"""Freeze a private NFL current-role shadow against pregame Kalshi contracts.

This research forecast is not a dashboard pick, qualified signal, executable
offer, or demonstrated edge. All source assets must predate the quote capture.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from decimal import Decimal
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re

from sportsbet.quant.kalshi_identity_coverage import _name
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_market_settlement import verify_cohort
from sportsbet.quant.nfl_recent_role_params import PRIOR_STRENGTH, SOURCE_SHA256


VERSION = "kalshi-nfl-current-role-shadow-v1"
STAT = {"pass_yds": "passing_yards", "rush_yds": "rushing_yards",
        "rec_yds": "receiving_yards", "receptions": "receptions"}
USAGE = {"pass_yds": "attempts", "rush_yds": "carries",
         "rec_yds": "targets", "receptions": "targets"}
SOURCES = {
    ("stats", 2024): (513240737, "2026-08-13T16:49:10Z", "847569d194ca3d96b5efcf91e6eac5e18780fc47568a713fd545a82d29d155c1"),
    ("stats", 2025): (513243463, "2026-08-13T16:51:22Z", "2a461becaa9adb3c93a3074a3a31f1e960162a50163371a2d34e28393b5fff10"),
    ("stats", 2026): (605933905, "2026-10-02T15:48:18Z", "ad728d131967bcd78d6e6a23b205a65db0bbb6f12bb7497eb15e70f36ebf1f85"),
    ("snaps", 2024): (301000083, "2025-10-06T06:51:20Z", "9ec66a0c755939b329d4eba3f90e716bb874b5a6544f325ba220f003991ff99f"),
    ("snaps", 2025): (585953424, "2026-09-24T12:50:31Z", "47220218fecda7af7ee5b0272a8ecce7c1bfb1f4e1f0a2c8c90047571728ce20"),
    ("snaps", 2026): (605418286, "2026-10-02T11:01:51Z", "fae0627d81f4ffa1802263ac0fad1a29f5c1986d5749a711bde7c50651498273"),
}
STATS_COLUMNS = ("player_id", "team", "season", "week", "season_type",
                 "passing_yards", "rushing_yards", "receiving_yards", "receptions",
                 "attempts", "carries", "targets")
SNAP_COLUMNS = ("pfr_player_id", "team", "season", "week", "offense_snaps")
MAX_SOURCE_BYTES = 2_000_000


def team(value: str) -> str:
    return {"LAR": "LA", "WSH": "WAS"}.get(value, value)


def identity_index(bundle_path: Path, capture: datetime) -> dict[str, set[tuple[str, str]]]:
    raw = bundle_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("Pinned NFL crosswalk changed")
    identity = json.loads(gzip.decompress(raw))["identity"]
    if (clock(identity["retrieved_at"]) > capture
            or hashlib.sha256(identity["response_text"].encode()).hexdigest()
                != identity["source_sha256"]):
        raise ValueError("NFL crosswalk source chronology or hash failed")
    raw_rows = list(csv.DictReader(io.StringIO(identity["response_text"])))
    gsis_counts = Counter(r["gsis_id"] for r in raw_rows)
    pfr_counts = Counter(r["pfr_id"] for r in raw_rows)
    espn_counts = Counter(r["espn_id"] for r in raw_rows)
    names: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in raw_rows:
        if (gsis_counts[row["gsis_id"]] != 1 or pfr_counts[row["pfr_id"]] != 1
                or espn_counts[row["espn_id"]] != 1
                or not re.fullmatch(r"00-[0-9]{7}", row["gsis_id"])
                or not re.fullmatch(r"[A-Za-z0-9]{1,20}", row["pfr_id"])):
            continue
        names[_name(row["display_name"])].add((row["gsis_id"], row["pfr_id"]))
    return names


def load_sources(root: Path, capture: datetime) -> tuple[list[dict], list[dict]]:
    """Read only six hash-pinned free release assets, with no provider call."""
    import polars as pl

    stats, snaps = [], []
    for (kind, year), (asset_id, updated, expected_hash) in SOURCES.items():
        if clock(updated) > capture:
            raise ValueError("NFL source was published after market capture")
        name = (f"stats_player_week_{year}.parquet" if kind == "stats"
                else f"snap_counts_{year}.parquet")
        path = root / name
        if (path.is_symlink() or not path.is_file()
                or not 0 < path.stat().st_size <= MAX_SOURCE_BYTES
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash):
            raise ValueError("Pinned NFL source file missing or changed")
        columns = STATS_COLUMNS if kind == "stats" else SNAP_COLUMNS
        frame = pl.read_parquet(path).select(columns).filter(pl.col("season") == year)
        if kind == "stats":
            stats.extend(frame.filter(pl.col("season_type") == "REG").to_dicts())
        else:
            snaps.extend(frame.filter(pl.col("week") <= 18).to_dicts())
    return stats, snaps


def _index(stats: list[dict], snaps: list[dict]):
    by_player: dict[str, dict[tuple[int, int], dict]] = defaultdict(dict)
    team_weeks: dict[tuple[int, int, str], list[dict]] = defaultdict(list)
    for row in stats:
        if row.get("season_type") != "REG" or row.get("season") not in (2024, 2025, 2026):
            continue
        player = row.get("player_id")
        if not player:
            continue
        key = (row["season"], row["week"])
        if key in by_player[player]:
            raise ValueError("Duplicate NFL player stat game")
        by_player[player][key] = row
        team_weeks[(row["season"], row["week"], team(row["team"]))].append(row)
    by_pfr: dict[str, dict[tuple[int, int], dict]] = defaultdict(dict)
    for row in snaps:
        pfr = row.get("pfr_player_id")
        if not pfr or row.get("season") not in (2024, 2025, 2026) or row.get("week", 99) > 18:
            continue
        key = (row["season"], row["week"])
        if key in by_pfr[pfr]:
            raise ValueError("Duplicate NFL offensive snap game")
        by_pfr[pfr][key] = row
    return by_player, by_pfr, team_weeks


def _player_history(gsis: str, pfr: str, stat: str, by_player: dict,
                    by_pfr: dict) -> list[dict]:
    observed = by_player.get(gsis, {})
    participation = by_pfr.get(pfr, {})
    # Any recorded offensive production or usage requires a participation
    # receipt, even when this particular market's statistic is zero. Otherwise
    # an observed game could vanish from one prop's recent-role window.
    for key, row in observed.items():
        played = any(row.get(field) not in (None, 0) for field in
                     (*STAT.values(), *USAGE.values()))
        if played and (
                key not in participation or not (participation[key].get("offense_snaps") or 0) > 0):
            raise ValueError("stat_without_offense_snap")
    games = []
    for (season, week), snap in sorted(participation.items()):
        if not (snap.get("offense_snaps") or 0) > 0:
            continue
        row = observed.get((season, week))
        if row is not None and team(row["team"]) != team(snap["team"]):
            raise ValueError("stat_snap_team_conflict")
        if row is not None and row.get(stat) is None:
            raise ValueError("missing_played_stat")
        value = row[stat] if row is not None else 0
        if (not isinstance(value, (int, float)) or not math.isfinite(value)
                or (stat == "receptions" and value < 0)):
            raise ValueError("invalid_played_stat")
        games.append(dict(season=season, week=week, team=team(snap["team"]), value=value,
                          zero_from_offense_snaps=row is None))
    return games


def _usage_context(gsis: str, current: list[dict], metric: str,
                   team_weeks: dict) -> dict:
    recent = current[-2:]
    player_total = team_total = 0.0
    teammates: Counter[str] = Counter()
    for game in recent:
        rows = team_weeks.get((game["season"], game["week"], game["team"]), [])
        for row in rows:
            value = row.get(metric)
            if value is None:
                continue
            if not isinstance(value, (int, float)) or value < 0:
                raise ValueError("invalid_team_usage")
            team_total += value
            if row["player_id"] == gsis:
                player_total += value
            else:
                teammates[row["player_id"]] += value
    if team_total <= 0 or player_total > team_total:
        raise ValueError("missing_team_usage")
    return dict(metric=metric, games=len(recent), reported_player_usage=player_total,
                reported_team_usage=team_total,
                recent_share=player_total/team_total,
                largest_teammate_share=(max(teammates.values())/team_total if teammates else 0.0))


def predict(market_archive: dict, cohort: dict, stats: list[dict], snaps: list[dict],
            identity: dict[str, set[tuple[str, str]]], *, now: datetime) -> dict:
    rows = verify_cohort(market_archive, cohort)
    if now.utcoffset() is None or now >= min(clock(r["scheduled_game_start_time"]) for r in rows):
        raise ValueError("Shadow model must freeze before every selected game")
    source = market_archive["evidence"]["sources"]["kalshi"]
    targets, teams = source["prop_inventory"]["targets"], source["targets"]
    by_player, by_pfr, team_weeks = _index(stats, snaps)
    results = []
    reasons: Counter[str] = Counter()
    for offer in rows:
        try:
            target = targets[offer["player_target_id"]]
            matches = identity.get(_name(target["player_name"]), set())
            if len(matches) != 1:
                raise ValueError("missing_or_ambiguous_identity")
            gsis, pfr = next(iter(matches))
            quoted_team = team(teams[offer["team_target_id"]]["details"]["abbreviation"])
            history = _player_history(gsis, pfr, STAT[offer["prop_type"]], by_player, by_pfr)
            if len(history) < 20:
                raise ValueError("fewer_than_20_offensive_games")
            sample = history[-20:]
            current = [g for g in sample if g["season"] == 2026 and g["team"] == quoted_team]
            older = [g for g in sample if g not in current]
            if len(current) < 2 or len(older) < 1 or [g["team"] for g in history[-2:]] != [quoted_team]*2:
                raise ValueError("insufficient_current_team_role")
            line = Decimal(str(offer["line"]))
            prior = (sum(g["value"] > line for g in older)+.5)/(len(older)+1)
            probability = (sum(g["value"] > line for g in current)+PRIOR_STRENGTH*prior)/(
                len(current)+PRIOR_STRENGTH)
            context = _usage_context(gsis, current, USAGE[offer["prop_type"]], team_weeks)
            results.append(dict(ticker=offer["ticker"], milestone_id=offer["milestone_id"],
                player_target_id=offer["player_target_id"], gsis_player_id=gsis,
                prop_type=offer["prop_type"], line=offer["line"],
                model_over_probability=probability, market_yes_midpoint=offer["market_midpoint"],
                sample_games=len(sample), current_team_games=len(current), older_games=len(older),
                snap_backed_zero_games=sum(g["zero_from_offense_snaps"] for g in sample),
                current_mean_stat=sum(g["value"] for g in current)/len(current),
                previous_mean_stat=sum(g["value"] for g in older)/len(older),
                teammate_context=context, roster_verified=False,
                execution_ready=False))
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            reason = str(exc)
            allowed = {"missing_or_ambiguous_identity", "stat_without_offense_snap",
                "stat_snap_team_conflict", "missing_played_stat", "invalid_played_stat",
                "fewer_than_20_offensive_games", "insufficient_current_team_role",
                "invalid_team_usage", "missing_team_usage"}
            reasons[reason if reason in allowed else "invalid_source_input"] += 1
    if len(results)+sum(reasons.values()) != len(rows):
        raise AssertionError("Shadow forecast denominator failed")
    results.sort(key=lambda r:r["ticker"])
    return dict(protocol=VERSION, generated_at=now.isoformat(),
        implementation_sha256=hashlib.sha256(
            Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        market_archive_sha256=cohort["market_archive_sha256"],
        market_selection_sha256=cohort["selection_sha256"],
        selected_contracts=len(rows), forecast_contracts=len(results),
        forecast_games=len({r["milestone_id"] for r in results}),
        unavailable_reasons=dict(sorted(reasons.items())),
        forecasts_sha256=digest(results), forecasts=results,
        model_version=VERSION, model_backtest_validated=False,
        current_roster_verified=False, model_forecasts_matched_to_live_price=False,
        edge_established=False, qualified_picks=0, execution_ready=False)


def build_report(market_archive: dict, cohort: dict, source_dir: Path,
                 *, now: datetime) -> dict:
    """Attach source receipts only after their bytes and prequote clocks pass."""
    capture = clock(cohort["captured_at"])
    stats, snaps = load_sources(source_dir, capture)
    identity = identity_index(Path(__file__).with_name("nfl_role_sources.json.gz"), capture)
    report = predict(market_archive, cohort, stats, snaps, identity, now=now)
    report["source_sha256"] = {
        f"{kind}_{year}": value[2] for (kind, year), value in sorted(SOURCES.items())}
    report["crosswalk_sha256"] = SOURCE_SHA256
    report["source_assets_prequote"] = True
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-archive", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("Output already exists")
    market_archive = json.loads(args.market_archive.read_text(encoding="utf-8"))
    cohort = json.loads(args.cohort.read_text(encoding="utf-8"))
    report = build_report(market_archive, cohort, args.source_dir,
                          now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps({key: report[key] for key in (
        "protocol", "generated_at", "selected_contracts", "forecast_contracts",
        "forecast_games", "unavailable_reasons", "forecasts_sha256",
        "edge_established", "qualified_picks")}, sort_keys=True))


if __name__ == "__main__":
    main()
