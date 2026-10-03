"""Freeze an outcome-blind NFL Kalshi market baseline from an archived capture.

This is a research denominator, not a model forecast, recommended pick, fill, or
settlement. Keep the resulting player-level file private.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re


VERSION = "kalshi-nfl-market-baseline-v1"
MARKETS = frozenset(("pass_yds", "rush_yds", "rec_yds", "receptions"))
MAX_ARCHIVE_BYTES = 25_000_000
MAX_QUOTES = 10_000


def encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: object) -> str:
    return hashlib.sha256(encode(value)).hexdigest()


def clock(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() is None:
        raise ValueError("Market chronology requires timezones")
    return result


def cost(side: object) -> Decimal | None:
    if side is None:
        return None
    if not isinstance(side, dict):
        raise ValueError("Invalid displayed side")
    try:
        price = Decimal(str(side["cost"]))
        size = Decimal(str(side["displayed_size"]))
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise ValueError("Invalid displayed side") from exc
    if not (Decimal(0) < price < Decimal(1) and size > 0 and price.is_finite() and size.is_finite()):
        raise ValueError("Invalid displayed side")
    return price


def freeze(archive: dict, frozen_at: str) -> dict:
    """Select one balanced displayed line per exact player/game/stat before kickoff."""
    evidence, summary = archive["evidence"], archive["summary"]
    # Match market_watch.digest's original canonical encoding, including spaces.
    source_hash = hashlib.sha256(json.dumps(
        evidence, sort_keys=True, allow_nan=False).encode()).hexdigest()
    if (source_hash != summary.get("evidence_sha256")
            or evidence.get("schema_version") != 2
            or evidence.get("sport") != summary.get("sport") != "nfl"
            or evidence.get("captured_at") != summary.get("captured_at")):
        raise ValueError("Market archive integrity or scope failed")
    capture = clock(evidence["captured_at"])
    freeze_time = clock(frozen_at)
    if freeze_time < capture:
        raise ValueError("Cohort cannot precede its quote capture")
    source = evidence["sources"]["kalshi"]
    inventory = source["prop_inventory"]
    coverage = inventory["coverage"]
    quotes = inventory["quotes"]
    if (source.get("status") != "observed"
            or source.get("partial_coverage") is not False
            or inventory.get("partial_coverage") is not False
            or coverage.get("discovery_complete") is not True
            or coverage.get("series_expected") != coverage.get("series_observed")
            or coverage.get("structured_quote_markets") != len(quotes)
            or not 0 < len(quotes) <= MAX_QUOTES):
        raise ValueError("Kalshi prop capture is incomplete or unbounded")
    games = {item["milestone"]["id"]: item["milestone"] for item in source["games"]}
    if len(games) != len(source["games"]):
        raise ValueError("Ambiguous captured game")
    targets = inventory["targets"]
    teams = source["targets"]
    selected: dict[tuple[str, str, str], tuple[tuple, dict]] = {}
    reasons = Counter()
    tickers: set[str] = set()
    for quote in quotes:
        if quote.get("prop_type") not in MARKETS:
            raise ValueError("Unsupported market in complete capture")
        game = games[quote["milestone_id"]]
        player = targets[quote["player_target_id"]]
        team_id = quote["team_target_id"]
        if (team_id not in teams
                or not isinstance(player.get("player_name"), str)
                or not player["player_name"].strip()
                or not isinstance(teams[team_id]["details"].get("abbreviation"), str)
                or not teams[team_id]["details"]["abbreviation"]
                or player["team_target_id"] != team_id
                or team_id not in (game["details"]["home_team_id"], game["details"]["away_team_id"])
                or clock(quote["scheduled_game_start_time"]) != clock(game["start_date"])
                or clock(quote["request_started_at"]) > clock(quote["received_at"])
                or clock(quote["received_at"]) > capture
                or capture - clock(quote["received_at"]) > timedelta(minutes=5)
                or clock(quote["received_at"]) >= clock(quote["scheduled_game_start_time"])):
            raise ValueError("Quote identity or chronology failed")
        for field in ("market_sha256", "rules_sha256", "source_page_sha256"):
            if re.fullmatch(r"[0-9a-f]{64}", str(quote.get(field))) is None:
                raise ValueError("Quote source commitment missing")
        try:
            line = Decimal(str(quote["line"]))
        except (InvalidOperation, KeyError, TypeError) as exc:
            raise ValueError("Invalid line") from exc
        if not line.is_finite() or line < Decimal(".5") or line % 1 != Decimal(".5"):
            raise ValueError("Invalid line")
        ticker = quote["ticker"]
        if not isinstance(ticker, str) or not ticker or ticker in tickers:
            raise ValueError("Missing or duplicate exact contract ticker")
        tickers.add(ticker)
        if clock(quote["scheduled_game_start_time"]) <= freeze_time:
            reasons["already_started_at_freeze"] += 1
            continue
        yes, no = cost(quote.get("yes_ask")), cost(quote.get("no_ask"))
        if yes is None or no is None:
            reasons["one_sided_or_unquoted"] += 1
            continue
        spread = yes + no - 1
        if spread < 0:
            raise ValueError("Crossed displayed market")
        midpoint = (yes + 1 - no) / 2
        key = (quote["milestone_id"], quote["player_target_id"], quote["prop_type"])
        row = {field: quote[field] for field in (
            "ticker", "milestone_id", "player_target_id", "team_target_id", "prop_type",
            "line", "received_at", "scheduled_game_start_time", "market_sha256",
            "rules_sha256", "source_page_sha256", "yes_ask", "no_ask")}
        row["market_midpoint"] = str(midpoint)
        row["displayed_spread"] = str(spread)
        row["settlement_equivalent"] = False
        row["execution_ready"] = False
        rank = (abs(midpoint - Decimal(".5")), spread, ticker)
        if key not in selected or rank < selected[key][0]:
            selected[key] = (rank, row)
    rows = [value[1] for _, value in sorted(selected.items())]
    return {
        "protocol": VERSION,
        "protocol_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "captured_at": evidence["captured_at"],
        "frozen_at": freeze_time.isoformat(),
        "market_archive_sha256": source_hash,
        "eligible_quote_lines": len(quotes),
        "excluded_quote_lines": dict(sorted(reasons.items())),
        "selected_contracts": len(rows),
        "selected_by_market": dict(sorted(Counter(row["prop_type"] for row in rows).items())),
        "selection_sha256": digest(rows),
        "selections": rows,
        "model_forecasts_matched": 0,
        "authenticated_settlements": 0,
        "edge_established": False,
        "execution_ready": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-archive", type=Path, required=True)
    parser.add_argument("--frozen-at", required=True, help="UTC decision time before all included games")
    parser.add_argument("--output", type=Path, required=True, help="Private, exclusive research output")
    args = parser.parse_args()
    if args.market_archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise SystemExit("Market archive exceeds size limit")
    result = freeze(json.loads(args.market_archive.read_text(encoding="utf-8")), args.frozen_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps({key: result[key] for key in (
        "protocol", "captured_at", "frozen_at", "market_archive_sha256",
        "eligible_quote_lines", "excluded_quote_lines", "selected_contracts",
        "selected_by_market", "selection_sha256", "edge_established", "execution_ready")},
        sort_keys=True))


if __name__ == "__main__":
    main()
