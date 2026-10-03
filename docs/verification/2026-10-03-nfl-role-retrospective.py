"""Aggregate-only retrospective role-model diagnostic; no market prices or edge claim."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import statistics

import pyarrow.parquet as pq

from sportsbet.quant import kalshi_role_shadow as role
from sportsbet.quant.kalshi_identity_coverage import _name


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--root", type=Path, required=True,
                    help="Private retained cohort.json, market-archive.json and sources/ directory")
parser.add_argument("--output", type=Path, help="Optional ignored aggregate JSON output")
args = parser.parse_args()
ROOT = args.root


def load():
    stats, snaps = [], []
    for (kind, year), (_, _, expected) in role.SOURCES.items():
        filename = (f"stats_player_week_{year}.parquet" if kind == "stats"
                    else f"snap_counts_{year}.parquet")
        path = ROOT / "sources" / filename
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Pinned NFL source file changed")
        columns = list(role.STATS_COLUMNS if kind == "stats" else role.SNAP_COLUMNS)
        if kind == "stats":
            columns += ["game_id", "opponent_team"]
        rows = pq.read_table(path, columns=columns).to_pylist()
        if kind == "stats":
            stats.extend(row for row in rows if row["season_type"] == "REG")
        else:
            snaps.extend(row for row in rows if row["week"] <= 18)
    return stats, snaps


def mean(values):
    return sum(values) / len(values) if values else None


def score(rows):
    if not rows:
        return {"rows": 0}
    games = defaultdict(list)
    for row in rows:
        games[row["game"]].append(row)
    result = {"rows": len(rows), "games": len(games),
              "players": len({row["player"] for row in rows})}
    for metric in ("brier", "log_loss"):
        game_values, player_values = {}, defaultdict(list)
        for game, items in games.items():
            weight = 1 / len(items)
            game_values[game] = mean([item["role_" + metric] - item["base_" + metric]
                                      for item in items])
            for item in items:
                player_values[item["player"]].append(
                    ((item["role_" + metric] - item["base_" + metric]) * weight,
                     weight))
        result["role_" + metric] = mean([mean([item["role_" + metric]
                                               for item in items]) for items in games.values()])
        result["base_" + metric] = mean([mean([item["base_" + metric]
                                               for item in items]) for items in games.values()])
        result["role_minus_base_" + metric] = mean(list(game_values.values()))
        keys = sorted(game_values)
        if len(keys) >= 2:
            rng = random.Random(20261003)
            draws = sorted(mean([game_values[rng.choice(keys)] for _ in keys])
                           for _ in range(2000))
            result["game_95_" + metric] = [draws[50], draws[1950]]
        else:
            result["game_95_" + metric] = None
        keys = sorted(player_values)
        if len(keys) >= 2:
            clusters = {player: (sum(value for value, _ in values),
                                 sum(weight for _, weight in values))
                        for player, values in player_values.items()}
            rng = random.Random(20261003)
            draws = []
            for _ in range(2000):
                sampled = [clusters[rng.choice(keys)] for _ in keys]
                draws.append(sum(value for value, _ in sampled)
                             / sum(weight for _, weight in sampled))
            draws.sort()
            result["player_95_" + metric] = [draws[50], draws[1950]]
        else:
            result["player_95_" + metric] = None
    return result


archive = json.loads((ROOT / "market-archive.json").read_text())
cohort = json.loads((ROOT / "cohort.json").read_text())
offers = role.verify_cohort(archive, cohort)
capture = role.clock(cohort["captured_at"])
if any(role.clock(updated) > capture for _, updated, _ in role.SOURCES.values()):
    raise ValueError("NFL source was published after market capture")
stats, snaps = load()
by_player, by_pfr, team_weeks = role._index(stats, snaps)
identity = role.identity_index(Path(role.__file__).with_name("nfl_role_sources.json.gz"), capture)
targets = archive["evidence"]["sources"]["kalshi"]["prop_inventory"]["targets"]
quoted = set()
unmatched = 0
for offer in offers:
    matches = identity.get(_name(targets[offer["player_target_id"]]["player_name"]), set())
    if len(matches) != 1:
        unmatched += 1
        continue
    quoted.add((*next(iter(matches)), offer["prop_type"]))

team_games = defaultdict(set)
for row in stats:
    if row.get("game_id"):
        team_games[(row["season"], row["week"], role.team(row["team"]))].add(row["game_id"])

out = []
reasons = Counter()
allowed_reasons = {
    "short_history", "short_current_role", "target_team_conflict",
    "missing_target_stat", "invalid_target_stat", "ambiguous_target_game",
    "stat_without_offense_snap", "stat_snap_team_conflict",
    "missing_played_stat", "invalid_played_stat", "invalid_team_usage",
    "missing_team_usage",
}
for gsis, pfr, prop in sorted(quoted):
    stat = role.STAT[prop]
    metric = role.USAGE[prop]
    for key, snap in sorted(by_pfr.get(pfr, {}).items()):
        season, week = key
        if season < 2025 or (snap.get("offense_snaps") or 0) <= 0:
            continue
        prior_stats = {past: row for past, row in by_player.get(gsis, {}).items() if past < key}
        prior_snaps = {past: row for past, row in by_pfr[pfr].items() if past < key}
        try:
            history = role._player_history(gsis, pfr, stat,
                                           {gsis: prior_stats}, {pfr: prior_snaps})
            if len(history) < 20:
                raise ValueError("short_history")
            sample = history[-20:]
            target_team = role.team(snap["team"])
            current = [game for game in sample
                       if game["season"] == season and game["team"] == target_team]
            older = [game for game in sample if game not in current]
            if (len(current) < 2 or not older
                    or [game["team"] for game in history[-2:]] != [target_team] * 2):
                raise ValueError("short_current_role")
            role._usage_context(gsis, current, metric, team_weeks)
            source = by_player.get(gsis, {}).get(key)
            if source is not None and role.team(source["team"]) != target_team:
                raise ValueError("target_team_conflict")
            if source is not None and source.get(stat) is None:
                raise ValueError("missing_target_stat")
            actual = source[stat] if source is not None else 0
            if not isinstance(actual, (int, float)) or not math.isfinite(actual):
                raise ValueError("invalid_target_stat")
            games = team_games[(season, week, target_team)]
            if source is not None and source.get("game_id"):
                game_id = source["game_id"]
            elif len(games) == 1:
                game_id = next(iter(games))
            else:
                raise ValueError("ambiguous_target_game")
            line = math.floor(statistics.median(game["value"] for game in history[-10:])) + .5
            older_p = (sum(game["value"] > line for game in older) + .5) / (len(older) + 1)
            role_p = (sum(game["value"] > line for game in current)
                      + role.PRIOR_STRENGTH * older_p) / (len(current) + role.PRIOR_STRENGTH)
            base_p = (sum(game["value"] > line for game in sample) + .5) / 21
            y = int(actual > line)
            result = {"season": season, "prop": prop, "game": game_id, "player": gsis,
                      "explicit_target_stat": source is not None}
            for label, probability in (("role", role_p), ("base", base_p)):
                result[label + "_brier"] = (probability - y) ** 2
                result[label + "_log_loss"] = -(y * math.log(probability)
                                                + (1 - y) * math.log1p(-probability))
            out.append(result)
            if source is None:
                reasons["target_zero_from_snap"] += 1
        except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
            reason = str(exc)
            reasons[reason if reason in allowed_reasons else "invalid_source_input"] += 1

report = {"source_sha256_verified": True,
          "scope": "retrospective synthetic half-line calibration, no bookmaker price or untouched holdout",
          "quoted_player_prop_pairs": len(quoted), "unmatched_contracts": unmatched,
          "attempted_positive_snap_player_prop_games": (
              len(out) + sum(value for key, value in reasons.items()
                             if key != "target_zero_from_snap")),
          "unavailable": dict(sorted(reasons.items())),
          "splits": {str(season): {prop: score([row for row in out
                                                   if row["season"] == season and row["prop"] == prop])
                                   for prop in role.STAT}
                     for season in (2025, 2026)},
          "explicit_target_stat_only": {
              str(season): {prop: score([row for row in out if row["season"] == season
                                        and row["prop"] == prop and row["explicit_target_stat"]])
                            for prop in role.STAT}
              for season in (2025, 2026)}}
encoded = json.dumps(report, sort_keys=True, indent=2, allow_nan=False)
if args.output is not None:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(encoded + "\n")
print(encoded)
