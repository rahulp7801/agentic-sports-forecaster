"""Offline prospective skill audit across independent NFL market/model pairs.

A pair must replay from its exact prequote sources and authentic venue results.
This comparison is forecasting research against a displayed midpoint and a
frozen prior-20 baseline. It never establishes executable betting edge.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from sportsbet.quant import kalshi_role_shadow_v2 as v3
from sportsbet.quant import kalshi_role_shadow_v4 as v4
from sportsbet.quant.kalshi_market_cohort import clock
from sportsbet.quant.kalshi_market_settlement import venue_results
from sportsbet.quant.kalshi_pair_capture import MAX_PAIR_BYTES, unpack
from sportsbet.quant.kalshi_role_shadow_eval import (
    _forward_bounds, evaluate, MAX_INPUT_BYTES,
)


VERSION = "kalshi-nfl-independent-pair-series-v1"
MAX_CASES = 64


def _game_keys(market: dict, cohort: dict) -> tuple[set[str], set[tuple[str, ...]]]:
    games = market["evidence"]["sources"]["kalshi"]["games"]
    by_id = {game["milestone"]["id"]: game["milestone"] for game in games}
    if len(by_id) != len(games):
        raise ValueError("Repeated game identity in market archive")
    ids, fixtures = set(), set()
    for offer in cohort["selections"]:
        game_id = offer["milestone_id"]
        game = by_id[game_id]
        details = game["details"]
        teams = tuple(sorted((details["home_team_id"], details["away_team_id"])))
        if (len(set(teams)) != 2
                or clock(game["start_date"]) != clock(offer["scheduled_game_start_time"])):
            raise ValueError("Selected game fixture changed")
        ids.add(game_id)
        fixtures.add((clock(game["start_date"]).isoformat(), *teams))
    if len(ids) != len(fixtures):
        raise ValueError("Ambiguous selected game fixture")
    return ids, fixtures


def _score(probability: Decimal, outcome: Decimal) -> tuple[Decimal, Decimal]:
    if not probability.is_finite() or not 0 < probability < 1:
        raise ValueError("Invalid frozen probability")
    return ((probability - outcome) ** 2,
            -(outcome * probability.ln()
              + (1 - outcome) * (1 - probability).ln()))


def _favorable(bounds: dict, comparator: str) -> bool:
    for metric in ("brier", "log_loss"):
        for cluster in ("game", "player"):
            interval = bounds[f"model_minus_{comparator}_{metric}_{cluster}_cluster_95"]
            if interval is None or Decimal(interval[1]) >= 0:
                return False
    return True


def aggregate(cases: list[dict], *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None or not 0 < len(cases) <= MAX_CASES:
        raise ValueError("Series clock or cohort count invalid")
    seen_ids: set[str] = set()
    seen_fixtures: set[tuple[str, ...]] = set()
    model_version = None
    selected = forecast_total = verified = 0
    selected_games: set[str] = set()
    verified_games: set[str] = set()
    states: Counter[str] = Counter()
    market_rows = []
    prior_rows = []
    cohort_hashes = []
    complete = True
    for case in cases:
        if set(case) != {"pair", "market_archive", "source_dir", "settlements"}:
            raise ValueError("Series case scope invalid")
        pair, market = case["pair"], case["market_archive"]
        cohort, shadow = unpack(pair)
        if shadow["protocol"] not in (v3.VERSION, v4.VERSION):
            raise ValueError("Series requires a forward source model")
        if model_version is None:
            model_version = shadow["protocol"]
        elif shadow["protocol"] != model_version:
            raise ValueError("Mixed model versions cannot establish a prospective series")
        ids, fixtures = _game_keys(market, cohort)
        if seen_ids & ids or seen_fixtures & fixtures:
            raise ValueError("Overlapping game cohorts cannot be counted twice")
        seen_ids.update(ids)
        seen_fixtures.update(fixtures)
        scored = evaluate(market, cohort, shadow, Path(case["source_dir"]),
                          case["settlements"], now=now)
        if not scored["price_contemporaneous_with_model"]:
            raise ValueError("Series includes a stale model/market pair")
        _, outcomes = venue_results(market, cohort, case["settlements"], now=now)
        offers = {offer["ticker"]: offer for offer in cohort["selections"]}
        for row in shadow["forecasts"]:
            offer = offers[row["ticker"]]
            state, result = outcomes[row["ticker"]]
            states[state] += 1
            if state != "venue_verified":
                continue
            outcome = Decimal(int(result == "yes"))
            model = _score(Decimal(str(row["model_over_probability"])), outcome)
            market_score = _score(Decimal(str(offer["market_midpoint"])), outcome)
            prior = _score(Decimal(str(row["prior20_over_probability"])), outcome)
            game, player = offer["milestone_id"], offer["player_target_id"]
            market_rows.append((game, player, model[0] - market_score[0],
                                model[1] - market_score[1]))
            prior_rows.append((game, player, model[0] - prior[0],
                               model[1] - prior[1]))
            verified_games.add(game)
            verified += 1
        selected += len(cohort["selections"])
        forecast_total += len(shadow["forecasts"])
        selected_games.update(ids)
        cohort_hashes.append(cohort["selection_sha256"])
        complete = complete and scored["complete"]
    market_bounds = _forward_bounds(market_rows, "market")
    prior_bounds = _forward_bounds(prior_rows, "prior20")
    minimum = len(verified_games) >= 50
    return dict(protocol=VERSION, model_version=model_version,
        cohort_count=len(cases), market_selection_sha256=sorted(cohort_hashes),
        selected_contracts=selected, selected_games=len(selected_games),
        forecast_contracts=forecast_total, verified_forecasts=verified,
        verified_games=len(verified_games), result_states=dict(sorted(states.items())),
        complete=complete, minimum_50_independent_games_met=minimum,
        market_comparison=market_bounds, prior20_comparison=prior_bounds,
        forecast_skill_gate_met=(complete and minimum
            and _favorable(market_bounds, "market")
            and _favorable(prior_bounds, "prior20")),
        displayed_midpoint_executable=False, fees_included=False,
        fills_verified=False, roi=None, clv=None, edge_established=False,
        qualified_picks=0, execution_ready=False)


def _read(path: Path, maximum: int) -> dict:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= maximum:
        raise ValueError("Series input missing or unbounded")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Series input must be an object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True,
                        help="Private JSON listing pair, market, source directory and settlement paths")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("Output already exists")
    manifest = _read(args.manifest, 100_000)
    if manifest.get("protocol") != VERSION or not 0 < len(manifest.get("cases", [])) <= MAX_CASES:
        parser.error("Invalid private series manifest")
    root = args.manifest.resolve().parent
    cases = []
    for paths in manifest["cases"]:
        if set(paths) != {"pair", "market_archive", "source_dir", "settlements"}:
            parser.error("Invalid private series case")
        cases.append(dict(
            pair=_read(root / paths["pair"], MAX_PAIR_BYTES),
            market_archive=_read(root / paths["market_archive"], MAX_INPUT_BYTES),
            source_dir=root / paths["source_dir"],
            settlements=_read(root / paths["settlements"], MAX_INPUT_BYTES)))
    result = aggregate(cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
    print(json.dumps({key: result[key] for key in (
        "protocol", "model_version", "cohort_count", "selected_games",
        "verified_games", "minimum_50_independent_games_met",
        "forecast_skill_gate_met", "edge_established", "qualified_picks")},
        sort_keys=True))


if __name__ == "__main__":
    main()
