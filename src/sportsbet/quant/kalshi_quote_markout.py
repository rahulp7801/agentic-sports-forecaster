"""Outcome-blind exact-contract ask movement after a frozen NFL decision.

This accepts only an independently captured, complete later public archive.
Ask movement is not a fill, liquidation price, closing line, win rate, or edge.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
import json
from pathlib import Path

from sportsbet.quant.kalshi_fee_score import (
    MAX_ARCHIVE_BYTES, POLICIES, _load, preoutcome,
)
from sportsbet.quant.kalshi_market_cohort import clock, digest, freeze


VERSION = "kalshi-nfl-exact-ask-markout-v1"
IDENTITY = ("event_ticker", "series_ticker", "milestone_id", "player_target_id",
            "team_target_id", "prop_type", "line", "rules_sha256",
            "scheduled_game_start_time", "strike_type")


def evaluate(pair: dict, original: dict, later: dict, *, policy: str = "role") -> dict:
    """Keep every frozen candidate in the denominator; score prelock asks only."""
    if policy not in POLICIES:
        raise ValueError("Unknown frozen ask policy")
    pre, _ = preoutcome(pair, original, policy=policy)
    later_capture = clock(later["evidence"]["captured_at"])
    original_quotes = {
        quote["ticker"]: quote
        for quote in original["evidence"]["sources"]["kalshi"]["prop_inventory"]["quotes"]
    }
    receipt = pair[POLICIES[policy][0]]
    earliest_start = min(clock(original_quotes[candidate["ticker"]]["scheduled_game_start_time"])
                         for candidate in receipt["candidates"])
    if not max(clock(pair["completed_at"]), clock(receipt["frozen_at"])) < later_capture < earliest_start:
        raise ValueError("Later market capture must be after decision and before all games")
    # Reuse the complete, hash-bound quote/game/target/chronology validator.
    freeze(later, later["evidence"]["captured_at"])
    later_quotes = later["evidence"]["sources"]["kalshi"]["prop_inventory"]["quotes"]
    later_by_ticker = {quote["ticker"]: quote for quote in later_quotes}
    if len(later_by_ticker) != len(later_quotes):
        raise ValueError("Duplicate later contract ticker")
    decision = clock(receipt["frozen_at"])
    counts: Counter[str] = Counter()
    movements: list[Decimal] = []
    by_game: dict[str, list[Decimal]] = defaultdict(list)
    rows = []
    for candidate in receipt["candidates"]:
        ticker = candidate["ticker"]
        old = original_quotes[ticker]
        quote = later_by_ticker.get(ticker)
        state, change = "missing_exact_contract", None
        if quote is not None:
            if any(old.get(field) != quote.get(field) for field in IDENTITY):
                state = "identity_changed"
            else:
                seen = clock(quote["received_at"])
                start = clock(old["scheduled_game_start_time"])
                if seen <= decision:
                    state = "not_later_than_decision"
                elif seen >= start-timedelta(hours=1):
                    state = "after_board_lock"
                else:
                    ask = quote.get(candidate["side"]+"_ask")
                    if not isinstance(ask, dict):
                        state = "side_unquoted"
                    else:
                        price = Decimal(str(ask.get("cost")))
                        size = Decimal(str(ask.get("displayed_size")))
                        if (not price.is_finite() or not Decimal(0)<price<Decimal(1)
                                or not size.is_finite() or size<1):
                            state = "side_unquoted"
                        else:
                            state = "prelock_exact_ask"
                            change = price-Decimal(candidate["displayed_ask"])
                            movements.append(change)
                            by_game[candidate["milestone_id"]].append(change)
        counts[state] += 1
        rows.append(dict(ticker=ticker, side=candidate["side"],
                         milestone_id=candidate["milestone_id"], state=state,
                         ask_change=str(change) if change is not None else None))
    if sum(counts.values()) != pre["candidates"]:
        raise AssertionError("Markout denominator changed")
    game_means = [sum(values)/len(values) for values in by_game.values()]
    return dict(protocol=VERSION, policy=policy,
        frozen_candidates=pre["candidates"], frozen_games=pre["candidate_games"],
        frozen_candidates_sha256=pre["candidates_sha256"],
        original_market_selection_sha256=pre["market_selection_sha256"],
        later_market_archive_sha256=later["summary"]["evidence_sha256"],
        later_captured_at=later["evidence"]["captured_at"],
        full_candidate_state_counts=dict(sorted(counts.items())),
        candidate_state_rows_sha256=digest(rows),
        prelock_matched_candidates=len(movements),
        prelock_matched_games=len(by_game),
        side_ask_up=sum(value>0 for value in movements),
        side_ask_down=sum(value<0 for value in movements),
        side_ask_unchanged=sum(value==0 for value in movements),
        mean_side_ask_change=(str(sum(movements)/len(movements)) if movements else None),
        equal_game_mean_side_ask_change=(str(sum(game_means)/len(game_means))
                                         if game_means else None),
        actual_fills_verified=False, closing_line_verified=False,
        edge_established=False, qualified_picks=0, roi=None, execution_ready=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", type=Path, required=True)
    parser.add_argument("--original-market-archive", type=Path, required=True)
    parser.add_argument("--later-market-archive", type=Path, required=True)
    parser.add_argument("--policy", choices=sorted(POLICIES), default="role")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("Output already exists")
    from sportsbet.quant.kalshi_pair_capture import MAX_PAIR_BYTES
    report = evaluate(_load(args.pair, MAX_PAIR_BYTES),
                      _load(args.original_market_archive, MAX_ARCHIVE_BYTES),
                      _load(args.later_market_archive, MAX_ARCHIVE_BYTES),
                      policy=args.policy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
