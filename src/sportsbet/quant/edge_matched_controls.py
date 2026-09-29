"""Offline matched-side controls for exploratory model-selection research."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import mean

from sportsbet.quant import edge_search_stress as search

PROTOCOL = {
    "version": "edge-matched-controls-v3",
    "policies": ["raw_model", "market_prior80"],
    "controls": ["always_over", "always_under", "half_each_side"],
    "scope": "Previously inspected historical data; exploratory attribution, never promotion",
}


def key(x):
    return x["unit"] + (x["row"]["sportsbook"], x["row"]["quote_source_sha256"])


def price_observations(rows, sport, version):
    """Price controls need no independent forecast-time no-vig pair.

    A first side may arrive before the opposite forecast and therefore have no
    baseline in frozen.observations. Its verified price is nevertheless available
    by the later selected decision. Keep chronology and source proof intact.
    """
    audit = search.frozen.audit
    result = []
    for row in rows:
        if (audit._eligible(row, sport, version) is None
                or not audit.quote_evidence_valid(row)
                or not audit.settlement_identity_valid(row)):
            continue
        if float(row["line"]) % 1 != .5 or row.get("push_probability") != 0:
            continue
        outcome = audit._verified_outcome(row)
        over = row["direction"] == "over"
        result.append({"row": row, "unit": search.frozen._unit(row),
                       "entry": search.frozen.utc_timestamp(row["captured_at"]),
                       "quote": search.frozen.utc_timestamp(row["quote_time"]),
                       "start": search.frozen.utc_timestamp(row["game_start_time"]),
                       "q": None,
                       "y": (int(outcome) if over else 1-int(outcome)) if type(outcome) is bool else None})
    return result


def opposite_at_decision(candidate, index):
    """Only an exact opposite quote actually retained before this decision."""
    x = candidate["x"]
    choices = [other for other in index.get(key(x), [])
               if other["row"]["direction"] != x["row"]["direction"]
               and other["entry"] <= candidate["decision"]
               and search.fresh(other, candidate["decision"])]
    # Newer forecasts retain the opposite source record inside their own
    # immutable receipt. This is a price leg, not a fabricated second forecast.
    if (search.frozen.verified_recorded_market_baseline(x["row"]) is not None
            and x["entry"] <= candidate["decision"] and search.fresh(x, candidate["decision"])):
        row = dict(x["row"],
                   prediction_id="embedded_opposite:"+x["row"]["prediction_id"],
                   direction="under" if x["row"]["direction"] == "over" else "over",
                   american_odds=x["row"]["market_opposite_american_odds"],
                   quote_source_record_sha256=x["row"]["market_opposite_quote_source_record_sha256"])
        # y is normalized to Over; the same authenticated half-line statistic
        # settles either side. No missing or unknown outcome is converted.
        choices.append(dict(x, row=row, evidence_origin="embedded_verified_opposite"))
    if not choices:
        return None, "missing_timely_opposite"
    if len({c["row"]["american_odds"] for c in choices}) != 1:
        return None, "conflicting_opposite_prices"
    other = min(choices, key=lambda c: (c["entry"], c["row"]["prediction_id"]))
    own_raw = 1/(1+search.profit(x["row"]["american_odds"]))
    other_raw = 1/(1+search.profit(other["row"]["american_odds"]))
    q_side = own_raw/(own_raw+other_raw)
    q_over = q_side if x["row"]["direction"] == "over" else 1-q_side
    if (abs(q_over-x["q"]) > 1e-10
            or (other["q"] is not None and abs(other["q"]-x["q"]) > 1e-10)):
        return None, "conflicting_market_baseline"
    return other, None


def net(x):
    if x["y"] is None:
        return None
    won = bool(x["y"]) == (x["row"]["direction"] == "over")
    return search.profit(x["row"]["american_odds"]) if won else -1.0


def summary(records, value):
    groups = defaultdict(list)
    for record in records:
        groups[record["game_id"]].append(value(record))
    values = [v for group in groups.values() for v in group]
    return {"decisions": len(values), "games": len(groups),
            "mean": mean(values) if values else None,
            "game_cluster_95": search.frozen.cluster_interval(groups)}


def compare(selected, observed):
    index = defaultdict(list)
    for x in observed:
        index[key(x)].append(x)
    records = []
    excluded = Counter()
    matched = []
    directions = Counter()
    for c in selected:
        x = c["x"]
        other, reason = opposite_at_decision(c, index)
        if reason:
            excluded[reason] += 1
            continue
        # Price eligibility never depends on the label. Report incomplete or
        # conflicting authenticated outcomes separately, without relabeling them.
        matched.append(x["row"]["prediction_id"])
        directions[x["row"]["direction"]] += 1
        if x["y"] is None or other["y"] is None:
            excluded["pending_pair"] += 1
            continue
        if x["y"] != other["y"]:
            excluded["conflicting_verified_outcomes"] += 1
            continue
        a, b = net(x), net(other)
        over, under = (a, b) if x["row"]["direction"] == "over" else (b, a)
        q = x["q"] if x["row"]["direction"] == "over" else 1-x["q"]
        won = int(bool(x["y"]) == (x["row"]["direction"] == "over"))
        market_ev = q*(c["profit"]+1)-1
        records.append({"game_id": x["unit"][0], "player_id": x["unit"][1],
                        "prediction_id": x["row"]["prediction_id"],
                        "opposite_id": other["row"]["prediction_id"],
                        "opposite_evidence_origin": other.get("evidence_origin", "retained_forecast"),
                        "direction": x["row"]["direction"],
                        "model": a, "always_over": over, "always_under": under,
                        "half_each_side": (a+b)/2, "market_expected_return": market_ev,
                        "predicted_probability": c["probability"], "market_probability": q,
                        "break_even_probability": 1/(c["profit"]+1), "won": won})
    controls = {}
    for control in PROTOCOL["controls"]:
        controls[control] = {
            "return": summary(records, lambda r: r[control]),
            "paired_model_minus_control": summary(records, lambda r: r["model"]-r[control]),
        }
    calibration = {}
    for side in ("over", "under"):
        rs = [r for r in records if r["direction"] == side]
        calibration[side] = {"decisions": len(rs), **{
            field: mean(r[field] for r in rs) if rs else None
            for field in ("won", "predicted_probability", "market_probability", "break_even_probability")}}
    return {"selected": len(selected), "matched_prices": len(matched),
            "directions": dict(directions), "excluded": dict(excluded),
            "model_return": summary(records, lambda r: r["model"]),
            "market_expected_return": summary(records, lambda r: r["market_expected_return"]),
            "realized_minus_market_expected": summary(records, lambda r: r["model"]-r["market_expected_return"]),
            "controls": controls, "calibration_by_selected_direction": calibration,
            "matched_ids": matched, "records": records, "promote": False}


def run(rows, sport, version):
    observed, excluded = search.frozen.observations(rows, sport, version)
    policies = {"raw_model": search.select_model(observed),
                "market_prior80": search.select_model(observed, True)}
    return {"sport": sport, "model_version": version, "source_exclusions": excluded,
            "policies": {name: compare(selected, price_observations(rows, sport, version)) for name, selected in policies.items()},
            "limitations": [
                "Controls inherit the model-selected player, game, market, line and book; they test direction choice, not the whole selection process.",
                "Half each side is an analytical equal-exposure reference, not an executed strategy.",
                "The baseline market probability is an estimate, not known truth.",
                "No threshold search or new historical holdout; previous outcomes were inspected.",
                "Game intervals do not correct for multiple research attempts or repeated players.",
                "Old model results do not establish performance of newer model versions."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-version", default="empirical-jeffreys-v4")
    args = parser.parse_args()
    rows = search.frozen.OfflineLedger(args.ledger_path).predictions()
    report = {"protocol": PROTOCOL, "observed_at": datetime.now(timezone.utc).isoformat(),
              "source_sha256": hashlib.sha256(args.ledger_path.read_bytes()).hexdigest(),
              "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "selection_sha256": hashlib.sha256(Path(search.__file__).read_bytes()).hexdigest(),
              "source_filter_sha256": hashlib.sha256(Path(search.frozen.__file__).read_bytes()).hexdigest(),
              "reports": {sport: run(rows, sport, args.model_version) for sport in ("nfl", "cfb", "nba")}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print("Matched-side research completed; results kept in requested private output")


if __name__ == "__main__":
    main()
