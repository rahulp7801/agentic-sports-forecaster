"""Freeze a plain prior-20 displayed-ask challenger before NFL venue outcomes.

The challenger shares the role model's exact pregame market and source receipt.
It is a zero-fee, unfilled research counterfactual, never a consumer pick.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from sportsbet.quant import kalshi_ask_policy as role_ask
from sportsbet.quant import kalshi_role_shadow_v2 as role
from sportsbet.quant import kalshi_role_shadow_v4 as role_v4
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_market_settlement import venue_results
from sportsbet.quant.kalshi_pair_capture import unpack


VERSION = "kalshi-nfl-prior20-displayed-ask-research-v1"


def freeze(pair: dict, *, decided_at: datetime | None = None) -> dict:
    cohort, shadow = unpack(pair)
    if shadow["protocol"] not in (role.VERSION, role_v4.VERSION):
        raise ValueError("Prior-20 ask policy requires a forward source receipt")
    offers = {row["ticker"]: row for row in cohort["selections"]}
    forecasts = shadow["forecasts"]
    if (len(offers) != len(cohort["selections"])
            or len(forecasts) != len({row["ticker"] for row in forecasts})
            or not {row["ticker"] for row in forecasts} <= set(offers)):
        raise ValueError("Prior-20 selection identity failed")
    eligible = []
    for forecast in forecasts:
        if "prior20_over_probability" not in forecast:
            raise ValueError("Missing frozen prior-20 probability")
        chosen = role_ask.decision(
            offers[forecast["ticker"]],
            {"model_over_probability": forecast["prior20_over_probability"]})
        if chosen is not None:
            eligible.append(chosen)
    candidates = role_ask.one_per_player_game(eligible)
    receipt = pair.get("prior20_ask_policy")
    frozen_at = (decided_at or
                 (clock(receipt["frozen_at"]) if isinstance(receipt, dict)
                  else datetime.now(timezone.utc)))
    if frozen_at.utcoffset() is None:
        raise ValueError("Prior-20 decision requires a timezone")
    start, end = clock(pair["started_at"]), clock(pair["completed_at"])
    oldest_quote = min(clock(row["received_at"]) for row in cohort["selections"])
    first_game = min(clock(row["scheduled_game_start_time"])
                     for row in cohort["selections"])
    if (not end <= frozen_at < first_game
            or not 0 <= (frozen_at-start).total_seconds() <= 30
            or not 0 <= (frozen_at-oldest_quote).total_seconds() <= 300):
        raise ValueError("Prior-20 decision exceeded the pregame timing window")
    return dict(protocol=VERSION, frozen_at=frozen_at.isoformat(),
                comparator_model_version=role.COMPARATOR_VERSION,
                market_selection_sha256=cohort["selection_sha256"],
                model_forecasts_sha256=shadow["forecasts_sha256"],
                minimum_gross_margin=str(role_ask.MIN_GROSS_MARGIN),
                model_forecasts=len(forecasts),
                model_unavailable=len(cohort["selections"])-len(forecasts),
                below_margin=len(forecasts)-len(eligible),
                eligible_before_player_game_cap=len(eligible),
                one_per_player_game_excluded=len(eligible)-len(candidates),
                candidates_count=len(candidates),
                candidate_games=len({row["milestone_id"] for row in candidates}),
                candidates_sha256=digest(candidates), candidates=candidates,
                zero_fee_unfilled_counterfactual=True,
                edge_established=False, qualified_picks=0, execution_ready=False)


def audit(pair: dict, market_archive: dict, source_dir,
          settlements: dict, *, now: datetime | None = None) -> dict:
    """Replay the pregame challenger and exact source before scoring results."""
    now = now or datetime.now(timezone.utc)
    cohort, shadow = unpack(pair)
    frozen = freeze(pair)
    if pair.get("prior20_ask_policy") != frozen:
        raise ValueError("Pregame prior-20 receipt changed")
    if (clock(frozen["frozen_at"]) > now
            or (role.build_report if shadow["protocol"] == role.VERSION
                else role_v4.build_report)(market_archive, cohort, source_dir,
                                           shadow["source_manifest"],
                                 now=clock(shadow["generated_at"])) != shadow):
        raise ValueError("Pregame source or model replay changed")
    _, states = venue_results(market_archive, cohort, settlements, now=now)
    counts = Counter()
    verified_games = set()
    paid = won = Decimal(0)
    for candidate in frozen["candidates"]:
        state, result = states[candidate["ticker"]]
        counts[state] += 1
        if state != "venue_verified":
            continue
        verified_games.add(candidate["milestone_id"])
        paid += Decimal(candidate["displayed_ask"])
        won += int(result == candidate["side"])
    if sum(counts.values()) != frozen["candidates_count"]:
        raise AssertionError("Prior-20 outcome denominator failed")
    return dict(protocol=VERSION, comparator_model_version=role.COMPARATOR_VERSION,
                market_selection_sha256=cohort["selection_sha256"],
                model_forecasts_sha256=shadow["forecasts_sha256"],
                candidates_sha256=frozen["candidates_sha256"],
                settlement_evidence_sha256=settlements["evidence_sha256"],
                cohort_contracts=len(cohort["selections"]),
                model_forecasts=frozen["model_forecasts"],
                model_unavailable=frozen["model_unavailable"],
                below_margin=frozen["below_margin"],
                one_per_player_game_excluded=frozen["one_per_player_game_excluded"],
                candidates=frozen["candidates_count"],
                candidate_games=frozen["candidate_games"],
                candidate_result_counts=dict(sorted(counts.items())),
                verified_candidates=counts["venue_verified"],
                verified_candidate_games=len(verified_games),
                verified_subset_displayed_cost=str(paid),
                verified_subset_gross_unit_profit=str(won-paid),
                complete=(frozen["candidates_count"] > 0 and
                          counts["venue_verified"] == frozen["candidates_count"]),
                zero_fee_unfilled_counterfactual=True,
                fees_included=False, fills_verified=False, roi=None, clv=None,
                edge_established=False, qualified_picks=0, execution_ready=False)


def compare(pair: dict, market_archive: dict, source_dir,
            settlements: dict, *, now: datetime | None = None) -> dict:
    """Compare precommitted rules only on shared, authenticated exposures."""
    role_report = role_ask.audit(pair, market_archive, source_dir, settlements, now=now)
    prior_report = audit(pair, market_archive, source_dir, settlements, now=now)
    role_choices = {(row["milestone_id"], row["player_target_id"]): row
                    for row in pair["ask_policy"]["candidates"]}
    prior_choices = {(row["milestone_id"], row["player_target_id"]): row
                     for row in pair["prior20_ask_policy"]["candidates"]}
    common = set(role_choices) & set(prior_choices)
    if (len(role_choices) != role_report["candidates"]
            or len(prior_choices) != prior_report["candidates"]):
        raise ValueError("Repeated candidate exposure")
    cohort, _ = unpack(pair)
    _, states = venue_results(market_archive, cohort, settlements, now=now)
    by_game = {}
    verified = same_contract = same_side = 0
    for game, player in sorted(common):
        role_row, prior_row = role_choices[game, player], prior_choices[game, player]
        same_contract += int(role_row["ticker"] == prior_row["ticker"])
        same_side += int(role_row["ticker"] == prior_row["ticker"]
                         and role_row["side"] == prior_row["side"])
        role_state, role_result = states[role_row["ticker"]]
        prior_state, prior_result = states[prior_row["ticker"]]
        if role_state != "venue_verified" or prior_state != "venue_verified":
            continue
        verified += 1
        role_profit = (Decimal(int(role_result == role_row["side"]))
                       - Decimal(role_row["displayed_ask"]))
        prior_profit = (Decimal(int(prior_result == prior_row["side"]))
                        - Decimal(prior_row["displayed_ask"]))
        by_game.setdefault(game, []).append(prior_profit-role_profit)
    game_means = {game: sum(values)/len(values) for game, values in by_game.items()}
    from sportsbet.quant.kalshi_role_shadow_eval import _interval
    return dict(protocol="kalshi-nfl-two-ask-policy-comparison-v1",
                market_selection_sha256=cohort["selection_sha256"],
                role_candidates=role_report["candidates"],
                prior20_candidates=prior_report["candidates"],
                common_player_game_exposures=len(common),
                role_only_exposures=len(role_choices)-len(common),
                prior20_only_exposures=len(prior_choices)-len(common),
                common_same_contract=same_contract,
                common_same_contract_and_side=same_side,
                both_venue_verified_exposures=verified,
                unavailable_common_exposures=len(common)-verified,
                both_verified_games=len(game_means),
                prior20_minus_role_gross_profit_on_common_verified=(
                    str(sum(sum(values) for values in by_game.values())) if verified else None),
                prior20_minus_role_equal_game_gross_profit=(
                    str(sum(game_means.values())/len(game_means)) if game_means else None),
                prior20_minus_role_equal_game_game_cluster_95=_interval({
                    game: (float(value), 1.0) for game, value in game_means.items()}),
                role_report=role_report, prior20_report=prior_report,
                zero_fee_unfilled_counterfactual=True, fees_included=False,
                fills_verified=False, roi=None, clv=None,
                edge_established=False, qualified_picks=0, execution_ready=False)


def _load(path: Path, maximum: int = role_ask.MAX_INPUT_BYTES) -> dict:
    if not 0 < path.stat().st_size <= maximum:
        raise ValueError("Prior-20 input exceeds size bound")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Prior-20 input must be an object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", type=Path, required=True)
    parser.add_argument("--market-archive", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--settlements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare-role", action="store_true",
                        help="Report both rules and authenticated shared exposures")
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("Output already exists")
    from sportsbet.quant.kalshi_pair_capture import MAX_PAIR_BYTES
    evaluator = compare if args.compare_role else audit
    report = evaluator(_load(args.pair, MAX_PAIR_BYTES), _load(args.market_archive),
                       args.source_dir, _load(args.settlements))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()