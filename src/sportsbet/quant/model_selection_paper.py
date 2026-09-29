"""Independent private prospective model-selection receipts and matched controls."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
from statistics import mean

from sportsbet.ledger import utc_timestamp
from sportsbet.quant import cross_book_forward as forward
from sportsbet.quant import cross_book_paper as storage
from sportsbet.quant import edge_search_stress as search
from sportsbet.quant import edge_matched_controls as controls
from sportsbet.quant.audit_storage import audit_database_url

PROTOCOL = {
    "version": "model-selection-paper-v1",
    "captured_after": "2026-09-30T00:00:00+00:00",
    "model_versions": dict(forward.PROTOCOL["model_versions"]),
    "history_policies": dict(forward.PROTOCOL["history_policies"]),
    "recommendation_policy_version": "confidence-floor-v2",
    "policies": {"raw_model": "model-selection-raw-v1", "market_prior80": "model-selection-prior80-v1"},
    "controls": ["always_over", "always_under", "half_each_side"],
    "review_games": 50, "minimum_decisions": 100,
    "cohort": "First 50 started games with valid timely receipts per sport/policy; all must settle. Never expand a completed cohort.",
    "family_streams": 6, "family_alpha": .05,
    "bootstrap_samples": 10000, "bootstrap_seed": 20260930,
    "automatic_promotion": False,
}
# Freeze dependencies independently of the older cross-book experiment.
FROZEN_DIGESTS = {'sportsbet.quant.market_challengers': 'bb99ceb40450f0fcbebeb3730e75211954628d1ec8cf410d167f1a3bbc84f4df', 'sportsbet.quant.market_baseline': 'bffd86272a1eac303acb57dbd0b246355b8d2d5b2ab4c39945d5e8d5c3af9404', 'sportsbet.quant.priced_market_audit': '6925b66315c7daeab86f0c1cab57c02c7abda9f237f6a80242dba94d8419a5be', 'sportsbet.ledger': 'e33611de7f85c376b2967f3d1f1bf4a02e80ce093d85c7a1182d29b8799fe2b1', 'sportsbet.model_contract': '96cac511ca3ae555e953985167a18639ef06148947c82a00d8b6c4bc241f4f29', 'sportsbet.ingestion.prop_odds': 'e5ca0fd05e4bfacbff670c925016526b24ae6f9cf8ed0e1d43762c670cbf5ad3', 'sportsbet.quant.cross_book_forward': '19f521967b42fa5fa4934b4de925e32208344c88dcfe4a43fab24f174336dd33', 'sportsbet.quant.cross_book_paper': '727ba7410142aeb2512f69b14329bee220830dd26ba6000c35328946328c9a91', 'sportsbet.quant.edge_search_stress': '9aa8f576e52a06e9b61c785477f13d111170ebf12975a7f80c07435c1402279e', 'sportsbet.quant.edge_matched_controls': 'ec45a84d4694f42a5949e890071c311f726d9b8019fb64b8048a36cb3c9e5667'}


def dependencies():
    result = forward.source_digests()
    for module in (forward, storage, search, controls):
        result[module.__name__] = hashlib.sha256(Path(module.__file__).read_text(encoding="utf-8").encode()).hexdigest()
    return result


def commitments():
    if dependencies() != FROZEN_DIGESTS:
        raise ValueError("Frozen model-selection dependencies changed; new protocol required")
    return {"dependencies": FROZEN_DIGESTS,
            "implementation": hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode()).hexdigest(),
            "protocol": storage.digest(PROTOCOL)}


def scoped(rows, sport, now):
    if sport not in PROTOCOL["model_versions"]:
        raise ValueError("Unsupported sport")
    cutoff = utc_timestamp(PROTOCOL["captured_after"])
    result = []
    for row in rows:
        if row.get("sport") != sport or row.get("model_version") != PROTOCOL["model_versions"][sport]:
            continue
        entered = utc_timestamp(row["captured_at"])
        if entered < cutoff:
            continue
        if entered > now:
            raise ValueError("Future forecast receipt")
        if row.get("recommendation_policy_version") != PROTOCOL["recommendation_policy_version"]:
            raise ValueError("Changed recommendation policy")
        policy = PROTOCOL["history_policies"].get(sport)
        if policy and row.get("history_policy_version") != policy:
            raise ValueError("Changed history policy")
        if min(utc_timestamp(row["quote_time"]), utc_timestamp(row["model_generated_at"])) < cutoff:
            continue
        result.append(storage.clean(row))
    return result


def prepare(rows, sport, now):
    if now < utc_timestamp(PROTOCOL["captured_after"]):
        return []
    commitment = commitments()
    rows = scoped(rows, sport, now)
    version = PROTOCOL["model_versions"][sport]
    observed, _ = search.frozen.observations(rows, sport, version)
    index = defaultdict(list)
    for x in controls.price_observations(rows, sport, version):
        index[controls.key(x)].append(x)
    result = []
    for policy, protocol in PROTOCOL["policies"].items():
        for c in search.select_model(observed, prior=policy == "market_prior80"):
            x = c["x"]; row = x["row"]
            opposite, reason = controls.opposite_at_decision(c, index)
            if reason:
                continue
            deadline = min(min(item["start"], item["quote"]+timedelta(seconds=300)) for item in (x, opposite))
            if not c["decision"] <= now < deadline:
                continue
            evidence = sorted((r for r in rows if (r["game_id"], r["player_id"]) == x["unit"][:2]),
                              key=lambda r: r["prediction_id"])
            selection = {field: row[field] for field in (
                "prediction_id", "game_id", "player_id", "prop_type", "line", "direction",
                "sportsbook", "american_odds", "game_start_time", "model_version")}
            selection.update(decision_at=c["decision"].isoformat(), probability=c["probability"],
                             estimated_return=c["ev"], market_probability=x["q"] if row["direction"] == "over" else 1-x["q"],
                             opposite_american_odds=opposite["row"]["american_odds"],
                             opposite_id=opposite["row"]["prediction_id"],
                             opposite_evidence_origin=opposite.get("evidence_origin", "retained_forecast"))
            body = dict(version=PROTOCOL["version"], policy=policy, sport=sport, selection=selection,
                        evidence=evidence, commitments=commitment)
            payload = storage.encode(body)
            if len(payload.encode()) > storage.MAX_BYTES:
                raise ValueError("Paper payload too large")
            result.append(dict(protocol=protocol, sport=sport, game_id=row["game_id"],
                               player_id=row["player_id"], prediction_id=row["prediction_id"],
                               decision_at=c["decision"], valid_until=deadline, payload=payload,
                               payload_sha256=hashlib.sha256(payload.encode()).hexdigest()))
    return result


async def record(pool, rows, sport):
    """Append private receipts after existing forecast commit; bounded and nonfatal."""
    import structlog
    try:
        prepared = prepare(rows, sport, datetime.now(timezone.utc))
        if not prepared:
            return
        async with asyncio.timeout(3):
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("SET LOCAL statement_timeout='2s'")
                    # One pipelined batch avoids a network round trip per player.
                    await conn.executemany(storage.INSERT_SQL, [[row[key] for key in (
                        "protocol", "sport", "game_id", "player_id", "prediction_id",
                        "decision_at", "valid_until", "payload", "payload_sha256")] for row in prepared])
    except Exception as exc:
        structlog.get_logger().warning("model_selection_receipt_unavailable", error_type=type(exc).__name__)


def cluster_summary(records, field):
    groups = defaultdict(list)
    for row in records:
        groups[row["game_id"]].append(row[field])
    values = [v for group in groups.values() for v in group]
    bounds = None
    if len(groups) >= 2:
        rng = random.Random(PROTOCOL["bootstrap_seed"])
        games = sorted(groups); draws = []
        for _ in range(PROTOCOL["bootstrap_samples"]):
            sample = [groups[rng.choice(games)] for _ in games]
            draws.append(sum(map(sum, sample))/sum(map(len, sample)))
        draws.sort()
        tail = PROTOCOL["family_alpha"]/(2*PROTOCOL["family_streams"])
        bounds = [draws[int(len(draws)*tail)], draws[min(len(draws)-1, int(len(draws)*(1-tail)))]]
    return dict(mean=mean(values) if values else None, games=len(groups), decisions=len(values),
                family_adjusted_game_interval=bounds)


def summarize(entries, errors, sport, policy, now):
    starts = {}
    for entry in entries:
        start = utc_timestamp(entry["selection"]["game_start_time"])
        game = entry["selection"]["game_id"]
        if game in starts and starts[game] != start:
            errors["conflicting_game_start"] += 1
        starts[game] = start
    ordered = sorted((start, game) for game, start in starts.items() if start <= now)
    chosen = {game for _, game in ordered[:PROTOCOL["review_games"]]}
    cohort = [entry for entry in entries if entry["selection"]["game_id"] in chosen]
    records = []; pending = 0
    for entry in cohort:
        outcome = entry["outcome"]
        if type(outcome) is not bool:
            pending += 1
            continue
        s = entry["selection"]
        model = search.profit(s["american_odds"]) if outcome else -1.
        opposite = -1. if outcome else search.profit(s["opposite_american_odds"])
        over, under = (model, opposite) if s["direction"] == "over" else (opposite, model)
        records.append(dict(game_id=s["game_id"], model=model, always_over=over, always_under=under,
                            half_each_side=(model+opposite)/2, model_minus_under=model-under,
                            brier=(s["probability"]-int(outcome))**2,
                            market_brier=(s["market_probability"]-int(outcome))**2,
                            brier_difference=(s["probability"]-int(outcome))**2-(s["market_probability"]-int(outcome))**2))
    scores = {key: cluster_summary(records, key) for key in (
        "model", "always_over", "always_under", "half_each_side", "model_minus_under", "brier", "market_brier", "brier_difference")}
    closed = len(chosen) == PROTOCOL["review_games"] and pending == 0
    adequate = closed and len(records) >= PROTOCOL["minimum_decisions"]
    def lower(key):
        interval = scores[key]["family_adjusted_game_interval"]
        return interval is not None and interval[0] > 0
    error_interval = scores["brier_difference"]["family_adjusted_game_interval"]
    supported = bool(adequate and not errors and lower("model") and lower("model_minus_under")
                     and error_interval and error_interval[1] < 0)
    status = ("invalid_evidence" if errors else "awaiting_start" if now < utc_timestamp(PROTOCOL["captured_after"])
              else "collecting_fixed_cohort" if len(chosen) < PROTOCOL["review_games"]
              else "awaiting_cohort_settlement" if pending else "insufficient_fixed_cohort" if not adequate
              else "review_required" if supported else "edge_not_demonstrated")
    return dict(sport=sport, policy=policy, protocol=PROTOCOL, status=status, promote=False,
                valid_receipts=len(entries), invalid_receipts=sum(errors.values()), errors=dict(errors),
                review_cohort_games=len(chosen), review_game_ids=sorted(chosen), cohort_pending=pending,
                decided=len(records), wins=sum(r["model"]>0 for r in records), scores=scores,
                excluded_later_or_unstarted_receipts=len(entries)-len(cohort), cohort_closed=closed,
                observed_at=now.isoformat(), scope="Private prospective hypothetical selections, not accepted dashboard picks or executed bets.")


def audit_receipts(receipts, predictions, sport, policy, now):
    protocol = PROTOCOL["policies"][policy]
    by_id = {r["prediction_id"]: r for r in predictions}
    entries = []; errors = Counter(); seen = set()
    for receipt in receipts:
        if receipt["sport"] != sport or receipt["protocol"] != protocol:
            continue
        try:
            identity = (receipt["game_id"], receipt["player_id"])
            if identity in seen:
                raise ValueError("duplicate_receipt")
            seen.add(identity)
            recorded = utc_timestamp(str(receipt["recorded_at"]))
            if recorded > now or hashlib.sha256(receipt["payload"].encode()).hexdigest() != receipt["payload_sha256"]:
                raise ValueError("receipt_hash_or_clock")
            body = json.loads(receipt["payload"])
            if body["commitments"] != commitments():
                raise ValueError("changed_implementation")
            evidence = body["evidence"]
            if not evidence or any(r["prediction_id"] not in by_id or storage.digest(r) != storage.digest(storage.clean(by_id[r["prediction_id"]])) for r in evidence):
                raise ValueError("changed_or_missing_forecast")
            matches = [r for r in prepare(evidence, sport, recorded)
                       if r["protocol"] == protocol and r["prediction_id"] == receipt["prediction_id"]]
            if len(matches) != 1 or matches[0]["payload_sha256"] != receipt["payload_sha256"]:
                raise ValueError("selection_not_reproducible")
            expected = matches[0]
            if any(str(expected[k]) != str(receipt[k]) for k in ("protocol", "sport", "game_id", "player_id", "prediction_id")):
                raise ValueError("receipt_identity")
            if any(utc_timestamp(str(receipt[k])) != expected[k] for k in ("decision_at", "valid_until")):
                raise ValueError("receipt_deadline")
            row = by_id[receipt["prediction_id"]]
            outcome = search.frozen.audit._verified_outcome(row)
            if type(outcome) is not bool or utc_timestamp(row["outcome_observed_at"]) > now:
                outcome = None
            entries.append(dict(selection=body["selection"], outcome=outcome))
        except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
            errors[str(exc) if isinstance(exc, ValueError) else type(exc).__name__] += 1
    return summarize(entries, errors, sport, policy, now)


def main():
    from dotenv import load_dotenv
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); load_dotenv()
    ledger = storage.PaperLedger(database_url=audit_database_url())
    with ledger.snapshot():
        with ledger.connect() as db:
            raw = db.execute("""SELECT protocol,sport,game_id,player_id,prediction_id,decision_at,
                valid_until,recorded_at,payload,payload_sha256 FROM paper_selections WHERE protocol=ANY(?)""",
                (list(PROTOCOL["policies"].values()),)).fetchall()
        keys = ("protocol", "sport", "game_id", "player_id", "prediction_id", "decision_at", "valid_until", "recorded_at", "payload", "payload_sha256")
        receipts = [dict(zip(keys, r, strict=True)) for r in raw]
        ledger.ids = sorted({r["prediction_id"] for receipt in receipts for r in json.loads(receipt["payload"])["evidence"]})
        predictions = ledger.predictions()
    now = datetime.now(timezone.utc)
    report = {sport: {policy: audit_receipts(receipts, predictions, sport, policy, now)
                     for policy in PROTOCOL["policies"]} for sport in PROTOCOL["model_versions"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print("Private model-selection paper audit completed")


if __name__ == "__main__":
    main()
