"""Authenticate the fixed venue capture before invoking its frozen primary scorer.

This offline handoff makes no market, source, result or order request.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from sportsbet.quant.kalshi_market_cohort import clock
from sportsbet.quant import kalshi_stat_only_forward_eval as frozen
from sportsbet.quant.kalshi_stat_only_next_eval import _input
from sportsbet.quant.kalshi_stat_only_prelock_paper_result import verify_capture_wrapper


def score(root: Path, *, now: datetime | None = None, preflight_only: bool = False) -> dict:
    pair, market, forecast, quotes, decisions = (
        frozen._pinned(root / relative, name) for name, relative in (
            ("pair", "verified-timely-pair-20261003/pair.json"),
            ("market", "verified-timely-pair-20261003/market-archive.json"),
            ("forecast", "kalshi-stat-only-probabilities-20261004.json"),
            ("quotes", "kalshi-stat-only-quotes-20261004.json"),
            ("decisions", "kalshi-stat-only-ask-decisions-20261004.json"),
        )
    )
    sources = root / "verified-timely-pair-20261003/sources"
    schedule = root / "team-share-sources/games.parquet"
    pre, _ = frozen.preflight(pair, market, forecast, quotes, decisions, sources, schedule)
    if preflight_only:
        return pre
    current = now or datetime.now(timezone.utc)
    if current.utcoffset() is None or current < clock(pre["first_eligible_settlement_at"]):
        raise ValueError("Fixed result scoring is premature; no settlement file opened")
    settlement, _ = _input(root / "stat-only-settlement-20261006.json", 30_000_000)
    verify_capture_wrapper(settlement, pre)
    return frozen.evaluate(pair, market, forecast, quotes, decisions, sources,
                           schedule, settlement, now=current)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if (args.output.exists() or args.output.is_symlink()
            or args.output.resolve().parent != (Path.cwd() / ".local").resolve()):
        parser.error("Output must be new and directly under private .local")
    report = score(args.evidence_root, preflight_only=args.preflight_only)
    if not args.preflight_only:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
