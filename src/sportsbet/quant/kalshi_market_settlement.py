"""Audit the frozen NFL Kalshi market comparator against exact venue results.

Collection reads only public settled-market metadata. Reports never become picks,
model backtests, fills, or cross-venue returns.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

from sportsbet.quant import kalshi_market_cohort as cohort_module


VERSION = "kalshi-nfl-market-settlement-audit-v1"
MAX_INPUT_BYTES = 30_000_000
MAX_CONTRACTS = 500
BATCH_SIZE = 20


def verify_cohort(market_archive: dict, cohort: dict) -> list[dict]:
    if not isinstance(cohort, dict) or cohort.get("protocol") != cohort_module.VERSION:
        raise ValueError("Unexpected frozen market protocol")
    reproduced = cohort_module.freeze(market_archive, cohort["frozen_at"])
    if reproduced != cohort:
        raise ValueError("Frozen market selection or source commitment changed")
    rows = cohort["selections"]
    if not 0 < len(rows) <= MAX_CONTRACTS or len({r["ticker"] for r in rows}) != len(rows):
        raise ValueError("Frozen market selection is unbounded or ambiguous")
    return rows


async def collect(market_archive: dict, cohort: dict, reader, *, now: datetime | None = None) -> dict:
    """At most 25 public GETs for exact precommitted tickers, only after games."""
    rows = verify_cohort(market_archive, cohort)
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None or now < max(
            cohort_module.clock(r["scheduled_game_start_time"]) for r in rows) + timedelta(hours=6):
        raise ValueError("Settlement collection is premature")
    tickers = sorted(r["ticker"] for r in rows)
    pages = []
    for offset in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[offset:offset+BATCH_SIZE]
        started = datetime.now(timezone.utc)
        try:
            body = await reader.settled_markets(batch, historical=False)
            page = dict(tickers=batch, request_started_at=started.isoformat(),
                        received_at=datetime.now(timezone.utc).isoformat(), body=body)
        except Exception as exc:
            # Provider errors are retained by type; never archive request headers.
            page = dict(tickers=batch, request_started_at=started.isoformat(),
                        received_at=datetime.now(timezone.utc).isoformat(),
                        error_type=type(exc).__name__)
        pages.append(page)
    evidence = dict(protocol=VERSION, selection_sha256=cohort["selection_sha256"], pages=pages)
    return dict(evidence=evidence, evidence_sha256=cohort_module.digest(evidence))


def _market_result(market: dict, row: dict, received: datetime) -> str:
    """Return YES/NO only for an exact, final, whole-dollar contract."""
    if market.get("status") not in ("settled", "finalized"):
        raise ValueError("not_final")
    if market.get("result") not in ("yes", "no"):
        raise ValueError("nonbinary_result")
    rules = {"primary": market.get("rules_primary"),
             "secondary": market.get("rules_secondary")}
    strike = market.get("custom_strike")
    try:
        identity_ok = (
            market["ticker"] == row["ticker"]
            and market["event_ticker"] == row["ticker"].rsplit("-", 1)[0]
            and market["market_type"] == "binary"
            and market["strike_type"] == "greater"
            and Decimal(str(market["floor_strike"])) == Decimal(str(row["line"]))
            and isinstance(strike, dict)
            and strike.get("football_player") == row["player_target_id"]
            and strike.get("football_team") == row["team_target_id"]
            and hashlib.sha256(json.dumps(
                rules, sort_keys=True, allow_nan=False).encode()).hexdigest() == row["rules_sha256"]
            and Decimal(str(market["notional_value_dollars"])) == 1
            and Decimal(str(market["settlement_value_dollars"])) ==
                (1 if market["result"] == "yes" else 0)
            and cohort_module.clock(market["settlement_ts"]) >
                cohort_module.clock(row["scheduled_game_start_time"])
            and cohort_module.clock(market["settlement_ts"]) <= received)
    except (KeyError, InvalidOperation, TypeError, ValueError):
        identity_ok = False
    if not identity_ok:
        raise ValueError("invalid_contract_or_settlement")
    return market["result"]


def venue_results(market_archive: dict, cohort: dict, settlement_archive: dict,
                  *, now: datetime | None = None) -> tuple[list[dict], dict[str, tuple[str, str | None]]]:
    """Validate the full denominator once; return only exact final YES/NO labels."""
    rows = verify_cohort(market_archive, cohort)
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Audit clock requires a timezone")
    evidence = settlement_archive["evidence"]
    if (settlement_archive.get("evidence_sha256") != cohort_module.digest(evidence)
            or evidence.get("protocol") != VERSION
            or evidence.get("selection_sha256") != cohort["selection_sha256"]
            or not isinstance(evidence.get("pages"), list)
            or len(evidence["pages"]) != (len(rows)+BATCH_SIZE-1)//BATCH_SIZE):
        raise ValueError("Settlement archive integrity or scope failed")
    expected = {r["ticker"]: r for r in rows}
    requested: set[str] = set()
    returned: dict[str, tuple[dict, datetime]] = {}
    failures: set[str] = set()
    for page in evidence["pages"]:
        batch = page["tickers"]
        if (not isinstance(batch, list) or not 0 < len(batch) <= BATCH_SIZE
                or len(batch) != len(set(batch)) or set(batch) & requested
                or not set(batch) <= set(expected)):
            raise ValueError("Settlement batch identity failed")
        requested.update(batch)
        started, received = (cohort_module.clock(page[key]) for key in
                             ("request_started_at", "received_at"))
        if (received < started or received > now or received-started > timedelta(minutes=1)
                or started <= max(cohort_module.clock(expected[t]["scheduled_game_start_time"])
                                  for t in batch)):
            raise ValueError("Settlement request chronology failed")
        if page.get("error_type"):
            if "body" in page or not isinstance(page["error_type"], str):
                raise ValueError("Conflicting provider response")
            failures.update(batch)
            continue
        body = page["body"]
        if not isinstance(body.get("markets"), list) or body.get("cursor"):
            raise ValueError("Incomplete settlement response")
        for market in body["markets"]:
            ticker = market.get("ticker") if isinstance(market, dict) else None
            if ticker not in batch or ticker in returned:
                raise ValueError("Unexpected or duplicate settlement contract")
            returned[ticker] = (market, received)
    if requested != set(expected):
        raise ValueError("Settlement requests missed frozen contracts")
    states: dict[str, tuple[str, str | None]] = {}
    for ticker, row in expected.items():
        if ticker in failures:
            states[ticker] = ("provider_unavailable", None)
            continue
        if ticker not in returned:
            states[ticker] = ("not_returned", None)
            continue
        market, received = returned[ticker]
        try:
            result = _market_result(market, row, received)
        except ValueError as exc:
            states[ticker] = (str(exc), None)
            continue
        states[ticker] = ("venue_verified", result)
    if len(states) != len(rows):
        raise AssertionError("Settlement denominator partition failed")
    return rows, states


def audit(market_archive: dict, cohort: dict, settlement_archive: dict,
          *, now: datetime | None = None) -> dict:
    rows, states = venue_results(market_archive, cohort, settlement_archive, now=now)
    counts = Counter(state for state, _ in states.values())
    brier: list[Decimal] = []
    per_game: dict[str, list[Decimal]] = defaultdict(list)
    for row in rows:
        state, result = states[row["ticker"]]
        if state != "venue_verified":
            continue
        probability = Decimal(row["market_midpoint"])
        score = (probability - (1 if result == "yes" else 0)) ** 2
        brier.append(score)
        per_game[row["milestone_id"]].append(score)
    total = len(rows)
    if sum(counts.values()) != total:
        raise AssertionError("Settlement denominator partition failed")
    return dict(protocol=VERSION, market_archive_sha256=cohort["market_archive_sha256"],
        selection_sha256=cohort["selection_sha256"],
        settlement_evidence_sha256=settlement_archive["evidence_sha256"],
        selected_contracts=total, selected_games=len({r["milestone_id"] for r in rows}),
        result_counts=dict(sorted(counts.items())),
        verified_games=len(per_game),
        verified_contract_brier=(str(sum(brier)/len(brier)) if brier else None),
        equal_verified_game_brier=(str(sum(sum(v)/len(v) for v in per_game.values())/len(per_game))
                                 if per_game else None),
        complete=counts["venue_verified"] == total,
        model_forecasts_matched=0, roi=None, clv=None,
        edge_established=False, execution_ready=False)


def _load(path: Path) -> dict:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("Research input exceeds size limit")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Research input must be an object")
    return value


def _save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-archive", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--settlements", type=Path,
                        help="Existing provider archive; omit only when collecting after all games")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("Output already exists; no provider read was made")
    market_archive, cohort = _load(args.market_archive), _load(args.cohort)
    if args.settlements:
        report = audit(market_archive, cohort, _load(args.settlements))
        _save(args.output, report)
        print(json.dumps(report, sort_keys=True))
    else:
        from sportsbet.ingestion.kalshi import KalshiReader

        async def run():
            async with KalshiReader() as reader:
                return await collect(market_archive, cohort, reader)

        result = asyncio.run(run())
        _save(args.output, result)
        print(json.dumps(dict(protocol=VERSION,
                              batches=len(result["evidence"]["pages"]),
                              evidence_sha256=result["evidence_sha256"],
                              execution_ready=False)))


if __name__ == "__main__":
    main()
