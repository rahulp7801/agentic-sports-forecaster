"""Private read-only scoring of prospective CFB team-role research receipts."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

from sportsbet.ledger import utc_timestamp
from sportsbet.model_contract import CFB_MODEL_VERSION
from sportsbet.quant.audit_storage import ReadOnlyLedger, audit_database_url
from sportsbet.quant.cfb_team_role_shadow import (
    VERSION, POLICY, MARKETS, digest, implementation_sha256, verified_recorded_shadow_probability)
from sportsbet.quant.history_tuning import Example, compare, score
from sportsbet.quant.market_baseline import verified_recorded_market_baseline
from sportsbet.quant.priced_market_audit import _eligible, _verified_outcome

PROTOCOL = "cfb-team-role-priced-forward-v1"
MIN_PAIRED_GAMES = 50


def evaluator_sha256() -> dict[str, str]:
    from sportsbet.quant import history_tuning, market_baseline, priced_market_audit
    paths = [Path(__file__), Path(history_tuning.__file__), Path(market_baseline.__file__),
             Path(priced_market_audit.__file__)]
    return {path.name: hashlib.sha256(path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").encode()).hexdigest() for path in paths}


def report(rows: list[dict], receipts: dict[str, tuple]) -> dict:
    result = dict(audit_protocol=PROTOCOL, model_version=VERSION, policy_version=POLICY,
        implementation_sha256=implementation_sha256(), evaluator_sha256=evaluator_sha256(),
        generated_at=datetime.now(timezone.utc).isoformat(), status="collecting",
        promote=False, minimum_paired_games=MIN_PAIRED_GAMES,
        scope="Research probabilities on future exact CFB offers; no bet or acceptance policy.",
        markets={})
    attempts = []
    for row in rows:
        shadow = row.get("cfb_team_role_shadow")
        if (row.get("sport") == "cfb" and isinstance(shadow, dict)
                and shadow.get("model_version") == VERSION
                and _eligible(row, "cfb", CFB_MODEL_VERSION) is not None):
            attempts.append(row)
    attempts.sort(key=lambda row: (utc_timestamp(row["captured_at"]),
        row["direction"] != "over", row["prediction_id"]))
    selected = {}
    for row in attempts:
        key = (row["game_id"], row["player_id"], row["prop_type"], float(row["line"]))
        selected.setdefault(key, row)  # Fix selection before observing result or price pairing.
    result.update(recorded_attempts=len(attempts), earliest_attempts=len(selected),
                  duplicate_attempts=len(attempts)-len(selected))
    for prop in sorted(MARKETS):
        cohort = [row for row in selected.values() if row["prop_type"] == prop]
        counts = Counter(attempts=len(cohort))
        examples = []
        for row in cohort:
            raw, recorded_at, payload_sha256 = receipts.get(row["prediction_id"], (None, None, None))
            try:
                stored = json.loads(raw) if isinstance(raw, str) else None
                current = {key: value for key, value in row.items() if key not in (
                    "prediction_id", "outcome", "outcome_source", "outcome_ref",
                    "outcome_observed_at", "actual_value", "outcome_evidence")}
                intact = isinstance(stored, dict) and digest(current) == digest(stored)
            except (TypeError, ValueError):
                intact = False
            candidate = (verified_recorded_shadow_probability(raw, recorded_at, payload_sha256)
                         if intact else None)
            if candidate is None:
                counts["unavailable"] += 1
                continue
            counts["verified_candidate"] += 1
            market = verified_recorded_market_baseline(row)
            if market is None:
                counts["unpaired_market"] += 1
                continue
            counts["paired_price"] += 1
            outcome = _verified_outcome(row)
            if type(outcome) is not bool:
                counts["pending_or_unverified"] += 1
                continue
            counts["paired_decided"] += 1
            examples.append((Example("evaluate", row["game_id"], row["player_id"],
                date.fromisoformat(row["game_date"]), float(row["line"]), int(outcome),
                float(row["model_probability"]), market, candidate, (),
                row["model_sample_size"], False), candidate, market))
        metric = dict(status="insufficient_data", promote=False,
            counts={key: counts[key] for key in ("attempts", "unavailable", "verified_candidate",
                "unpaired_market", "paired_price", "pending_or_unverified", "paired_decided")},
            paired_games=len({item[0].game for item in examples}),
            paired_players=len({item[0].player for item in examples}))
        if examples:
            e = [item[0] for item in examples]
            base = np.asarray([item.base for item in e])
            candidate = np.asarray([item[1] for item in examples])
            market = np.asarray([item[2] for item in examples])
            metric.update(production=score(e, base), candidate=score(e, candidate),
                          market=score(e, market),
                          candidate_minus_production=compare(e, base, candidate),
                          candidate_minus_market=compare(e, market, candidate))
            if metric["paired_games"] >= MIN_PAIRED_GAMES:
                supported = all(metric[name][measure+"_"+cluster+"_95"] is not None
                    and metric[name][measure+"_"+cluster+"_95"][1] < 0
                    for name in ("candidate_minus_production", "candidate_minus_market")
                    for measure in ("brier", "log_loss") for cluster in ("game", "player"))
                metric["status"] = "predictive_evidence_supported" if supported else "evidence_not_demonstrated"
        result["markets"][prop] = metric
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv()
    try:
        ledger = ReadOnlyLedger(database_url=audit_database_url())
        with ledger.snapshot():
            rows = ledger.predictions()
            with ledger.connect() as db:
                raw_receipts = db.execute("""SELECT id,payload,recorded_at,payload_sha256
                    FROM predictions WHERE recorded_at IS NOT NULL
                    AND payload::jsonb->>'sport'='cfb'""").fetchall()
        receipts = {key: (raw, recorded_at, sha) for key, raw, recorded_at, sha in raw_receipts}
        result = report(rows, receipts)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        print(json.dumps({"attempts": result["earliest_attempts"], "status": result["status"]}))
    except Exception as exc:
        raise SystemExit(f"CFB role audit unavailable ({type(exc).__name__})") from None


if __name__ == "__main__":
    main()

