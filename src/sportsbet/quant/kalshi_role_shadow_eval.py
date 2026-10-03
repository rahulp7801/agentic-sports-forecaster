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

from sportsbet.quant.kalshi_market_cohort import clock
from sportsbet.quant.kalshi_market_settlement import venue_results
from sportsbet.quant.kalshi_role_shadow import VERSION as SHADOW_VERSION, build_report


VERSION = "kalshi-nfl-role-market-paired-v1"
MAX_INPUT_BYTES = 30_000_000


def evaluate(market_archive: dict, cohort: dict, shadow: dict, source_dir: Path,
             settlements: dict, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None or shadow.get("protocol") != SHADOW_VERSION:
        raise ValueError("Invalid shadow protocol or audit clock")
    generated = clock(shadow["generated_at"])
    if generated > now or build_report(market_archive, cohort, source_dir, now=generated) != shadow:
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
    game_log_deltas: dict[str, list[Decimal]] = defaultdict(list)
    for forecast in forecasts:
        offer = by_offer[forecast["ticker"]]
        state, result = states[forecast["ticker"]]
        counts[state] += 1
        if state != "venue_verified":
            continue
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
    if sum(counts.values()) != len(forecasts):
        raise AssertionError("Paired forecast denominator failed")
    total = len(model_scores)
    game_means = [sum(values)/len(values) for values in game_deltas.values()]
    game_log_means = [sum(values)/len(values) for values in game_log_deltas.values()]
    return dict(protocol=VERSION,
        market_selection_sha256=cohort["selection_sha256"],
        shadow_forecasts_sha256=shadow["forecasts_sha256"],
        settlement_evidence_sha256=settlements["evidence_sha256"],
        cohort_contracts=len(selection), shadow_forecasts=len(forecasts),
        shadow_unavailable=len(selection)-len(forecasts),
        paired_venue_verified=total, paired_verified_games=len(game_deltas),
        paired_result_counts=dict(sorted(counts.items())),
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
        price_contemporaneous_with_model=False,
        market_midpoint_executable=False,
        roi=None, clv=None, edge_established=False, qualified_picks=0,
        execution_ready=False)


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
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--shadow", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--settlements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("Output already exists")
    report = evaluate(_load(args.market_archive), _load(args.cohort),
        _load(args.shadow), args.source_dir, _load(args.settlements))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
