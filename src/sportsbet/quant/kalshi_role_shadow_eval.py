"""Paired prospective Brier comparison for a frozen NFL shadow and market.

The captured market midpoint is a forecasting benchmark, not a live offer.
This audit cannot assert edge, execution, ROI, or a consumer pick.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import random

from sportsbet.quant.kalshi_market_cohort import clock
from sportsbet.quant.kalshi_market_settlement import venue_results
from sportsbet.quant.kalshi_pair_capture import unpack
from sportsbet.quant.kalshi_role_shadow import VERSION as SHADOW_VERSION, build_report
from sportsbet.quant import kalshi_role_shadow_v2, kalshi_role_shadow_v4


VERSION = "kalshi-nfl-role-market-paired-v1"
FORWARD_VERSION = "kalshi-nfl-role-market-paired-v4"
FORWARD_ALIAS_VERSION = "kalshi-nfl-role-market-paired-v5"
MAX_INPUT_BYTES = 30_000_000
BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 20261003


def _interval(groups: dict[str, tuple[float, float]]) -> list[str] | None:
    """Deterministic whole-cluster percentile interval for a weighted mean."""
    if len(groups) < 2:
        return None
    keys = sorted(groups)
    rng = random.Random(BOOTSTRAP_SEED)
    draws = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sampled = [groups[rng.choice(keys)] for _ in keys]
        numerator = sum(value for value, _ in sampled)
        denominator = sum(weight for _, weight in sampled)
        draws.append(numerator / denominator)
    draws.sort()
    return [str(draws[int(BOOTSTRAP_SAMPLES * .025)]),
            str(draws[int(BOOTSTRAP_SAMPLES * .975)])]


def _forward_bounds(rows: list[tuple[str, str, Decimal, Decimal]],
                    comparator: str = "market") -> dict:
    """Give games equal weight, then player/games, then prop contracts."""
    if comparator not in ("market", "prior20"):
        raise ValueError("Unexpected forward comparator")
    games: dict[str, dict[str, list[tuple[Decimal, Decimal]]]] = defaultdict(
        lambda: defaultdict(list))
    for game, player, brier, log_loss in rows:
        games[game][player].append((brier, log_loss))
    result = {"paired_verified_players": len({player for _, player, _, _ in rows}),
              "cluster_interval_method": "deterministic 10000 whole-cluster percentile resamples; equal game, player/game and contract weights"}
    for index, metric in enumerate(("brier", "log_loss")):
        game_groups = {}
        game_values = {}
        player_groups: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for game in sorted(games):
            by_player = games[game]
            game_total = Decimal(0)
            for player in sorted(by_player):
                values = by_player[player]
                player_mean = sum(value[index] for value in values) / len(values)
                game_total += player_mean / len(by_player)
                player_groups[player].append((float(player_mean / len(by_player)),
                                              1 / len(by_player)))
            game_values[game] = game_total
            game_groups[game] = (float(game_total), 1.0)
        grouped_players = {player: (sum(value for value, _ in entries),
                                    sum(weight for _, weight in entries))
                           for player, entries in player_groups.items()}
        prefix = f"model_minus_{comparator}_{metric}"
        result[prefix + "_equal_game"] = (str(sum(game_values.values()) / len(game_values))
                                                   if game_values else None)
        result[prefix + "_game_cluster_95"] = _interval(game_groups)
        result[prefix + "_player_cluster_95"] = _interval(grouped_players)
    return result


def evaluate(market_archive: dict, cohort: dict, shadow: dict, source_dir: Path,
             settlements: dict, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None or shadow.get("protocol") not in (
            SHADOW_VERSION, kalshi_role_shadow_v2.VERSION, kalshi_role_shadow_v4.VERSION):
        raise ValueError("Invalid shadow protocol or audit clock")
    generated = clock(shadow["generated_at"])
    if generated > now or generated < clock(cohort["frozen_at"]):
        raise ValueError("Frozen shadow chronology changed")
    replay = (build_report(market_archive, cohort, source_dir, now=generated)
              if shadow["protocol"] == SHADOW_VERSION else
              (kalshi_role_shadow_v2.build_report if shadow["protocol"] == kalshi_role_shadow_v2.VERSION
               else kalshi_role_shadow_v4.build_report)(market_archive, cohort, source_dir,
                                                        shadow["source_manifest"], now=generated))
    if replay != shadow:
        raise ValueError("Frozen shadow source or forecast changed")
    selection, states = venue_results(market_archive, cohort, settlements, now=now)
    by_offer = {row["ticker"]: row for row in selection}
    forecasts = shadow["forecasts"]
    if (len(forecasts) != len({r["ticker"] for r in forecasts})
            or not {r["ticker"] for r in forecasts} <= set(by_offer)):
        raise ValueError("Shadow selection identity failed")
    counts: Counter[str] = Counter()
    model_scores: list[Decimal] = []
    market_scores: list[Decimal] = []
    game_deltas: dict[str, list[Decimal]] = defaultdict(list)
    model_log_scores: list[Decimal] = []
    market_log_scores: list[Decimal] = []
    prior20_scores: list[Decimal] = []
    prior20_log_scores: list[Decimal] = []
    game_log_deltas: dict[str, list[Decimal]] = defaultdict(list)
    quote_ages: list[Decimal] = []
    forward_rows: list[tuple[str, str, Decimal, Decimal]] = []
    forward_prior_rows: list[tuple[str, str, Decimal, Decimal]] = []
    contemporaneous = 0
    contemporaneous_verified = 0
    for forecast in forecasts:
        offer = by_offer[forecast["ticker"]]
        state, result = states[forecast["ticker"]]
        counts[state] += 1
        age = Decimal(str((generated-clock(offer["received_at"])).total_seconds()))
        quote_ages.append(age)
        timely = Decimal(0) <= age <= Decimal(300)
        contemporaneous += int(timely)
        if state != "venue_verified":
            continue
        contemporaneous_verified += int(timely)
        try:
            model_p = Decimal(str(forecast["model_over_probability"]))
            market_p = Decimal(str(offer["market_midpoint"]))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Invalid frozen probability") from exc
        if not (0 < model_p < 1 and 0 < market_p < 1):
            raise ValueError("Invalid frozen probability")
        outcome = Decimal(1 if result == "yes" else 0)
        model_score = (model_p-outcome)**2
        market_score = (market_p-outcome)**2
        model_log_score = -(outcome*model_p.ln()+(1-outcome)*(1-model_p).ln())
        market_log_score = -(outcome*market_p.ln()+(1-outcome)*(1-market_p).ln())
        model_scores.append(model_score)
        market_scores.append(market_score)
        model_log_scores.append(model_log_score)
        market_log_scores.append(market_log_score)
        game_deltas[offer["milestone_id"]].append(market_score-model_score)
        game_log_deltas[offer["milestone_id"]].append(market_log_score-model_log_score)
        if shadow["protocol"] in (kalshi_role_shadow_v2.VERSION, kalshi_role_shadow_v4.VERSION):
            forward_rows.append((offer["milestone_id"], offer["player_target_id"],
                                 model_score-market_score, model_log_score-market_log_score))
            try:
                prior_p = Decimal(str(forecast["prior20_over_probability"]))
            except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
                raise ValueError("Invalid frozen prior-20 comparator") from exc
            if not prior_p.is_finite() or not 0 < prior_p < 1:
                raise ValueError("Invalid frozen prior-20 comparator")
            prior_score = (prior_p-outcome)**2
            prior_log_score = -(outcome*prior_p.ln()+(1-outcome)*(1-prior_p).ln())
            prior20_scores.append(prior_score)
            prior20_log_scores.append(prior_log_score)
            forward_prior_rows.append((offer["milestone_id"], offer["player_target_id"],
                                       model_score-prior_score,
                                       model_log_score-prior_log_score))
    if sum(counts.values()) != len(forecasts):
        raise AssertionError("Paired forecast denominator failed")
    total = len(model_scores)
    game_means = [sum(values)/len(values) for values in game_deltas.values()]
    game_log_means = [sum(values)/len(values) for values in game_log_deltas.values()]
    report = dict(protocol=(VERSION if shadow["protocol"] == SHADOW_VERSION
                          else FORWARD_VERSION if shadow["protocol"] == kalshi_role_shadow_v2.VERSION
                          else FORWARD_ALIAS_VERSION),
        market_selection_sha256=cohort["selection_sha256"],
        shadow_forecasts_sha256=shadow["forecasts_sha256"],
        settlement_evidence_sha256=settlements["evidence_sha256"],
        cohort_contracts=len(selection), shadow_forecasts=len(forecasts),
        shadow_unavailable=len(selection)-len(forecasts),
        paired_venue_verified=total, paired_verified_games=len(game_deltas),
        paired_result_counts=dict(sorted(counts.items())),
        quote_age_seconds_min=str(min(quote_ages)) if quote_ages else None,
        quote_age_seconds_max=str(max(quote_ages)) if quote_ages else None,
        quote_pairs_within_5m=contemporaneous,
        verified_pairs_within_5m=contemporaneous_verified,
        model_verified_subset_brier=str(sum(model_scores)/total) if total else None,
        market_verified_subset_brier=str(sum(market_scores)/total) if total else None,
        paired_market_minus_model_brier=(str((sum(market_scores)-sum(model_scores))/total)
                                         if total else None),
        equal_verified_game_market_minus_model_brier=(str(sum(game_means)/len(game_means))
                                                      if game_means else None),
        model_verified_subset_log_loss=str(sum(model_log_scores)/total) if total else None,
        market_verified_subset_log_loss=str(sum(market_log_scores)/total) if total else None,
        paired_market_minus_model_log_loss=(
            str((sum(market_log_scores)-sum(model_log_scores))/total) if total else None),
        equal_verified_game_market_minus_model_log_loss=(
            str(sum(game_log_means)/len(game_log_means)) if game_log_means else None),
        complete=total == len(forecasts),
        minimum_50_independent_games_met=len(game_deltas) >= 50,
        price_contemporaneous_with_model=bool(forecasts) and contemporaneous == len(forecasts),
        market_midpoint_executable=False,
        roi=None, clv=None, edge_established=False, qualified_picks=0,
        execution_ready=False)
    if shadow["protocol"] in (kalshi_role_shadow_v2.VERSION, kalshi_role_shadow_v4.VERSION):
        report.update(_forward_bounds(forward_rows))
        report.update(_forward_bounds(forward_prior_rows, "prior20"))
        report.update(comparator_model_version=kalshi_role_shadow_v2.COMPARATOR_VERSION,
            prior20_verified_subset_brier=(str(sum(prior20_scores)/total) if total else None),
            prior20_verified_subset_log_loss=(str(sum(prior20_log_scores)/total) if total else None))
    return report


def _load(path: Path) -> dict:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("Research input exceeds size limit")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Research input must be an object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-archive", type=Path, required=True)
    parser.add_argument("--cohort", type=Path)
    parser.add_argument("--shadow", type=Path)
    parser.add_argument("--pair", type=Path, help="Fresh pair receipt instead of separate cohort/shadow files")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--settlements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("Output already exists")
    if bool(args.pair) == bool(args.cohort and args.shadow) or (
            args.pair and (args.cohort or args.shadow)):
        parser.error("Supply either --pair or both --cohort and --shadow")
    cohort, shadow = (unpack(_load(args.pair)) if args.pair else
                      (_load(args.cohort), _load(args.shadow)))
    report = evaluate(_load(args.market_archive), cohort, shadow,
        args.source_dir, _load(args.settlements))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
