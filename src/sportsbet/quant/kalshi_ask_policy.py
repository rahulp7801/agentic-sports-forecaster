"""Precommit a displayed-ask NFL research rule before venue outcomes exist.

This is a zero-fee, unfilled counterfactual. It never qualifies a consumer pick.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

from sportsbet.quant import kalshi_role_shadow_v2 as role
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_market_settlement import venue_results
from sportsbet.quant.kalshi_pair_capture import MAX_PAIR_BYTES, unpack


VERSION = "kalshi-nfl-displayed-ask-research-v1"
MIN_GROSS_MARGIN = Decimal("0.05")
MAX_INPUT_BYTES = 30_000_000


def decision(offer: dict, forecast: dict) -> dict | None:
    try:
        probability = Decimal(str(forecast["model_over_probability"]))
        yes = Decimal(str(offer["yes_ask"]["cost"]))
        no = Decimal(str(offer["no_ask"]["cost"]))
        yes_size = Decimal(str(offer["yes_ask"]["displayed_size"]))
        no_size = Decimal(str(offer["no_ask"]["displayed_size"]))
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise ValueError("Invalid frozen model or displayed ask") from exc
    if not (all(value.is_finite() for value in (
            probability, yes, no, yes_size, no_size))
            and 0 < probability < 1 and 0 < yes < 1 and 0 < no < 1
            and yes + no >= 1 and yes_size > 0 and no_size > 0):
        raise ValueError("Invalid frozen model or displayed ask")
    yes_gap = probability - yes
    no_gap = 1 - probability - no
    side, gap, ask, size, win_probability = (
        ("yes", yes_gap, yes, yes_size, probability)
        if yes_gap >= no_gap else
        ("no", no_gap, no, no_size, 1-probability))
    if gap < MIN_GROSS_MARGIN:
        return None
    return dict(ticker=offer["ticker"], milestone_id=offer["milestone_id"],
                player_target_id=offer["player_target_id"],
                side=side, displayed_ask=str(ask), displayed_size=str(size),
                model_win_probability=str(win_probability), gross_margin=str(gap))


def freeze(pair: dict, *, decided_at: datetime | None = None) -> dict:
    cohort, shadow = unpack(pair)
    if shadow["protocol"] != role.VERSION:
        raise ValueError("Displayed-ask policy requires a forward source receipt")
    offers = {row["ticker"]: row for row in cohort["selections"]}
    forecasts = shadow["forecasts"]
    if (len(offers) != len(cohort["selections"])
            or len(forecasts) != len({row["ticker"] for row in forecasts})
            or not {row["ticker"] for row in forecasts} <= set(offers)):
        raise ValueError("Displayed-ask selection identity failed")
    candidates = []
    for forecast in forecasts:
        offer = offers[forecast["ticker"]]
        chosen = decision(offer, forecast)
        if chosen is not None:
            candidates.append(chosen)
    candidates.sort(key=lambda row: row["ticker"])
    # Read the clock after the last decision. A slow calculation must not
    # inherit the earlier model-completion timestamp as its decision time.
    frozen_at = (decided_at or
                 (clock(pair["ask_policy"]["frozen_at"])
                  if isinstance(pair.get("ask_policy"), dict) else
                  datetime.now(timezone.utc)))
    if frozen_at.utcoffset() is None:
        raise ValueError("Displayed-ask decision requires a timezone")
    start, end = clock(pair["started_at"]), clock(pair["completed_at"])
    oldest_quote = min(clock(row["received_at"]) for row in cohort["selections"])
    first_game = min(clock(row["scheduled_game_start_time"])
                     for row in cohort["selections"])
    if (not end <= frozen_at < first_game
            or not 0 <= (frozen_at-start).total_seconds() <= 30
            or not 0 <= (frozen_at-oldest_quote).total_seconds() <= 300):
        raise ValueError("Displayed-ask decision exceeded the pregame timing window")
    return dict(protocol=VERSION, frozen_at=frozen_at.isoformat(),
                market_selection_sha256=cohort["selection_sha256"],
                model_forecasts_sha256=shadow["forecasts_sha256"],
                minimum_gross_margin=str(MIN_GROSS_MARGIN),
                model_forecasts=len(forecasts),
                model_unavailable=len(cohort["selections"])-len(forecasts),
                below_margin=len(forecasts)-len(candidates),
                candidates_count=len(candidates),
                candidate_games=len({row["milestone_id"] for row in candidates}),
                candidates_sha256=digest(candidates), candidates=candidates,
                zero_fee_unfilled_counterfactual=True,
                edge_established=False, qualified_picks=0, execution_ready=False)


def audit(pair: dict, market_archive: dict, source_dir: Path,
          settlements: dict, *, now: datetime | None = None) -> dict:
    """Replay the pregame rule and source receipt before scoring exact outcomes."""
    now = now or datetime.now(timezone.utc)
    cohort, shadow = unpack(pair)
    frozen = freeze(pair)
    if pair.get("ask_policy") != frozen:
        raise ValueError("Pregame displayed-ask policy receipt changed")
    if (clock(frozen["frozen_at"]) > now
            or role.build_report(market_archive, cohort, source_dir,
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
        raise AssertionError("Displayed-ask outcome denominator failed")
    return dict(protocol=VERSION, market_selection_sha256=cohort["selection_sha256"],
                model_forecasts_sha256=shadow["forecasts_sha256"],
                candidates_sha256=frozen["candidates_sha256"],
                settlement_evidence_sha256=settlements["evidence_sha256"],
                cohort_contracts=len(cohort["selections"]),
                model_forecasts=frozen["model_forecasts"],
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


def _load(path: Path, maximum: int = MAX_INPUT_BYTES) -> dict:
    if not 0 < path.stat().st_size <= maximum:
        raise ValueError("Displayed-ask input exceeds bound")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Displayed-ask input must be an object")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", type=Path, required=True)
    parser.add_argument("--market-archive", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--settlements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("Output already exists")
    report = audit(_load(args.pair, MAX_PAIR_BYTES), _load(args.market_archive),
                   args.source_dir, _load(args.settlements))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
