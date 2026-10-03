"""Freeze a private NFL model/market research pair from an existing fresh archive.

This command makes no provider request. A timely displayed midpoint is still
not an executable offer, qualified pick, or established edge.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from sportsbet.quant.kalshi_market_cohort import MAX_ARCHIVE_BYTES, clock, freeze
from sportsbet.quant.kalshi_market_settlement import MAX_CONTRACTS
from sportsbet.quant.kalshi_role_shadow import build_report
from sportsbet.quant import kalshi_role_shadow_v4


VERSION = "kalshi-nfl-contemporaneous-pair-v1"
MAX_PAIR_BYTES = 5_000_000
MAX_BUILD_SECONDS = Decimal(30)
MAX_QUOTE_AGE_SECONDS = Decimal(300)


def capture(market_archive: dict, source_dir: Path, *, started_at: datetime,
            completed_at: datetime | None = None,
            source_manifest: dict | None = None) -> dict:
    """Fail closed if any selected quote ages out during model construction."""
    if started_at.utcoffset() is None:
        raise ValueError("Pair capture requires a timezone")
    cohort = freeze(market_archive, started_at.isoformat())
    rows = cohort["selections"]
    if not 0 < len(rows) <= MAX_CONTRACTS:
        raise ValueError("Pair capture has no bounded pregame market cohort")
    first_quote = min(clock(row["received_at"]) for row in rows)
    if not 0 <= (started_at-first_quote).total_seconds() <= 300:
        raise ValueError("Market quotes are not fresh at pair capture")
    shadow = (build_report(market_archive, cohort, source_dir, now=started_at)
              if source_manifest is None else
              kalshi_role_shadow_v4.build_report(market_archive, cohort, source_dir,
                                                 source_manifest, now=started_at))
    completed = completed_at or datetime.now(timezone.utc)
    if completed.utcoffset() is None:
        raise ValueError("Pair completion requires a timezone")
    build_seconds = Decimal(str((completed-started_at).total_seconds()))
    age_seconds = Decimal(str((completed-first_quote).total_seconds()))
    if (not Decimal(0) <= build_seconds <= MAX_BUILD_SECONDS
            or not Decimal(0) <= age_seconds <= MAX_QUOTE_AGE_SECONDS):
        raise ValueError("Pair capture exceeded the model/quote timing window")
    if not shadow["forecast_contracts"]:
        raise ValueError("Pair capture has no source-backed model forecasts")
    return dict(protocol=VERSION, started_at=started_at.isoformat(),
        completed_at=completed.isoformat(), build_seconds=str(build_seconds),
        oldest_quote_age_seconds=str(age_seconds),
        market_selection_sha256=cohort["selection_sha256"],
        forecasts_sha256=shadow["forecasts_sha256"],
        selected_contracts=cohort["selected_contracts"],
        forecast_contracts=shadow["forecast_contracts"],
        cohort=cohort, shadow=shadow,
        displayed_midpoint_executable=False, current_roster_verified=False,
        edge_established=False, qualified_picks=0, execution_ready=False)


def unpack(value: dict) -> tuple[dict, dict]:
    """Validate the pair envelope before independently replaying its receipts."""
    if not isinstance(value, dict) or value.get("protocol") != VERSION:
        raise ValueError("Invalid contemporaneous pair protocol")
    cohort, shadow = value["cohort"], value["shadow"]
    start, end = clock(value["started_at"]), clock(value["completed_at"])
    if (clock(cohort["frozen_at"]) != start
            or clock(shadow["generated_at"]) != start
            or not 0 <= (end-start).total_seconds() <= 30
            or cohort["selection_sha256"] != value["market_selection_sha256"]
            or shadow["forecasts_sha256"] != value["forecasts_sha256"]
            or len(cohort["selections"]) != value["selected_contracts"]
            or len(shadow["forecasts"]) != value["forecast_contracts"]
            or not shadow["forecasts"]
            or not 0 <= (end-min(clock(r["received_at"]) for r in cohort["selections"])
                        ).total_seconds() <= 300):
        raise ValueError("Contemporaneous pair chronology or commitment failed")
    return cohort, shadow


def save_pair(value: dict, output: Path) -> None:
    """Keep player-level research out of snapshots and public artifact staging."""
    encoded = json.dumps(value, sort_keys=True, indent=2, allow_nan=False)
    if len(encoded.encode()) > MAX_PAIR_BYTES:
        raise ValueError("Pair receipt exceeds its size limit")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(encoded)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-archive", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path,
                        help="Official release metadata staged before this market capture")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("Output already exists")
    if not 0 < args.market_archive.stat().st_size <= MAX_ARCHIVE_BYTES:
        parser.error("Market archive is empty or exceeds its size limit")
    archive = json.loads(args.market_archive.read_text(encoding="utf-8"))
    try:
        manifest = (json.loads(args.source_manifest.read_text(encoding="utf-8"))
                    if args.source_manifest else None)
        result = capture(archive, args.source_dir, started_at=datetime.now(timezone.utc),
                         source_manifest=manifest)
    except (KeyError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    save_pair(result, args.output)
    print(json.dumps({key: result[key] for key in (
        "protocol", "started_at", "completed_at", "selected_contracts",
        "forecast_contracts", "market_selection_sha256", "forecasts_sha256",
        "oldest_quote_age_seconds", "edge_established", "qualified_picks")},
        sort_keys=True))


if __name__ == "__main__":
    main()
