"""Versioned, untraded CFB current-team candidate on exact pregame offers.

The existing exploratory candidate was chosen in retrospective research whose historical source timing
does not support an edge claim. Only newly recorded, source-committed forecasts
can support promotion. Never use this probability to admit a consumer pick.
"""
from __future__ import annotations

import base64
from datetime import date, datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import zlib

from sportsbet.ingestion.provenance import STAT_FIELDS, stat_row_sha256
from sportsbet.model_contract import CFB_HISTORY_POLICY, CFB_MODEL_VERSION
from sportsbet.prop.query_builder import PROP_COLUMN_MAP

VERSION = "cfb-team-role-shadow-v1"
POLICY = "cfb-last-observed-team-research-v1"
PRIOR_STRENGTH = 20
MARKETS = frozenset(("pass_yds", "rush_yds", "rec_yds", "receptions"))
MAX_PLAYERS = 200
MAX_INPUT_BYTES = 100_000
ROW_FIELDS = STAT_FIELDS["cfb"]
SOURCE_FIELDS = ("source_provider", "source_sha256", "source_record_sha256",
                 "source_observed_at", "history_policy_version")
REASONS = frozenset(("unsupported_offer", "invalid_quote", "invalid_roster",
    "history_read_failed", "invalid_history", "insufficient_history",
    "no_current_team_history", "baseline_history_mismatch", "invalid_shadow_input"))


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode()).hexdigest()


def offer_digest(payload: dict) -> str:
    from sportsbet.ledger import utc_timestamp
    keys = ("game_id", "player_id", "prop_type", "direction", "line", "sportsbook",
            "american_odds", "quote_time", "quote_source_provider", "quote_source_sha256",
            "quote_source_record_sha256", "captured_at", "model_generated_at",
            "model_version", "history_policy_version", "history_observed_before",
            "forecast_cutoff", "model_probability", "model_sample_size",
            "game_start_time")
    values = {key: payload.get(key) for key in keys}
    for key in ("quote_time", "captured_at", "model_generated_at",
                "game_start_time", "history_observed_before"):
        values[key] = utc_timestamp(values[key]).isoformat()
    return digest(values)


@lru_cache(maxsize=1)
def implementation_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_text(encoding="utf-8-sig").replace("\r\n", "\n").encode()).hexdigest()


def _pack(rows: list[dict]) -> dict:
    raw = json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("invalid_history")
    return {"codec": "zlib-json-v1", "sha256": hashlib.sha256(raw).hexdigest(),
            "data": base64.b64encode(zlib.compress(raw, 9)).decode("ascii")}


def _unpack(value: dict) -> list[dict]:
    if not isinstance(value, dict) or value.get("codec") != "zlib-json-v1":
        raise ValueError("invalid_history")
    encoded = value.get("data")
    if not isinstance(encoded, str) or len(encoded) > MAX_INPUT_BYTES:
        raise ValueError("invalid_history")
    packed = base64.b64decode(encoded, validate=True)
    decoder = zlib.decompressobj()
    raw = decoder.decompress(packed, MAX_INPUT_BYTES + 1)
    if (len(raw) > MAX_INPUT_BYTES or decoder.unconsumed_tail
            or decoder.unused_data or not decoder.eof):
        raise ValueError("invalid_history")
    if hashlib.sha256(raw).hexdigest() != value.get("sha256"):
        raise ValueError("invalid_history")
    rows = json.loads(raw)
    if not isinstance(rows, list) or len(rows) > 40:
        raise ValueError("invalid_history")
    return rows


async def load_inputs(pool, season: int, cutoff: date, observed_before: datetime,
                      requests: set[tuple[str, str]]) -> dict[tuple[str, str], list[dict]]:
    """Read the same forty most recent non-null rows per athlete and stat as production."""
    if (observed_before.utcoffset() is None or not isinstance(cutoff, date)
            or len({player for player, _ in requests}) > MAX_PLAYERS
            or any(prop not in MARKETS or not player.isascii() or not player.isdecimal()
                   or not 0 < int(player) <= 2**63-1 for player, prop in requests)):
        raise ValueError("invalid_history")
    result = {}
    if not requests:
        return result
    fields = ",".join("e.game_id::bigint AS game_id" if field == "game_id" else "e." + field
                      for field in (*ROW_FIELDS, *SOURCE_FIELDS))
    async with pool.acquire() as conn:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            for prop in sorted({prop for _, prop in requests}):
                column = PROP_COLUMN_MAP[prop]  # Static allowlist, never caller SQL.
                ids = sorted({int(player) for player, market in requests if market == prop})
                rows = await conn.fetch(f"""WITH ranked AS (
                    SELECT {fields}, row_number() OVER (
                        PARTITION BY e.athlete_id ORDER BY e.game_date DESC,e.game_id DESC) rn
                    FROM cfb_effective_gamelogs e
                    WHERE e.athlete_id=ANY($1::bigint[]) AND e.season >= $2
                      AND e.{column} IS NOT NULL AND e.game_date < $3
                      AND e.source_observed_at <= $4
                      AND (e.supplement_manifest IS NULL OR EXISTS (
                          SELECT 1 FROM cfb_receiving_supplements s
                          WHERE s.athlete_id=e.athlete_id AND s.game_id=e.game_id
                            AND s.source_sha256=e.source_sha256 AND s.inserted_at <= $4))
                ) SELECT * FROM ranked WHERE rn<=40
                  ORDER BY athlete_id,game_date,game_id""",
                    ids, season-2, cutoff, observed_before, timeout=5)
                for item in rows:
                    row = dict(item)
                    row.pop("rn")
                    row = {key: value.isoformat() if isinstance(value, (date, datetime))
                           else value for key, value in row.items()}
                    result.setdefault((str(row["athlete_id"]), prop), []).append(row)
    return result


def shadow_record(payload: dict, rows: list[dict], *, unavailable: str | None = None) -> dict:
    from sportsbet.ledger import quote_evidence_valid, settlement_identity_valid, utc_timestamp
    result = dict(model_version=VERSION, policy_version=POLICY,
                  implementation_sha256=implementation_sha256(),
                  status="unavailable", generated_at=payload.get("captured_at"))
    try:
        if unavailable:
            raise ValueError(unavailable)
        if (payload.get("sport") != "cfb" or payload.get("prop_type") not in MARKETS
                or payload.get("model_version") != CFB_MODEL_VERSION
                or payload.get("history_policy_version") != CFB_HISTORY_POLICY
                or payload.get("direction") not in ("over", "under")):
            raise ValueError("unsupported_offer")
        now = utc_timestamp(payload["captured_at"])
        cutoff = date.fromisoformat(payload["game_date"])
        observed_before = utc_timestamp(payload["history_observed_before"])
        start = utc_timestamp(payload["game_start_time"])
        quote = utc_timestamp(payload["quote_time"])
        if (payload.get("forecast_cutoff") != payload["game_date"]
                or utc_timestamp(payload["model_generated_at"]) != now
                or not observed_before <= now < start
                or not 0 <= (now-quote).total_seconds() <= 300
                or not quote_evidence_valid(payload)
                or not settlement_identity_valid(payload)):
            raise ValueError("invalid_quote")
        availability = payload.get("availability")
        if (not isinstance(availability, dict)
                or availability.get("status") != "observed"
                or availability.get("roster_confirmed") is not True
                or availability.get("player_id") != payload["player_id"]
                or not isinstance(availability.get("team"), str)
                or not re.fullmatch(r"[A-Za-z0-9]{1,10}", availability["team"])
                or not re.fullmatch(r"[0-9a-f]{64}", availability.get("roster_source_sha256", ""))
                or not re.fullmatch(
                    r"https://site\.api\.espn\.com/apis/site/v2/sports/football/college-football/teams/[1-9][0-9]*/roster(?:\?limit=1000)?",
                    availability.get("roster_source_url", ""))
                or not 0 <= (now-utc_timestamp(availability["captured_at"])).total_seconds() <= 3600):
            raise ValueError("invalid_roster")
        line = float(payload["line"])
        if (not math.isfinite(line) or line < .5 or line % 1 != .5
                or payload.get("push_probability") != 0):
            raise ValueError("unsupported_offer")
        if not isinstance(rows, list) or not 20 <= len(rows) <= 40:
            raise ValueError("insufficient_history")
        season = cutoff.year if cutoff.month >= 8 else cutoff.year-1
        column = PROP_COLUMN_MAP[payload["prop_type"]]
        if len({row.get("game_id") for row in rows if isinstance(row, dict)}) != len(rows):
            raise ValueError("invalid_history")
        if any((earlier["game_date"], earlier["game_id"]) >=
               (later["game_date"], later["game_id"])
               for earlier, later in zip(rows, rows[1:])):
            raise ValueError("invalid_history")
        for row in rows:
            provider_policy = {
                "sportsdataverse_espn": "primary-v1",
                "sportsdataverse_espn_supplement": "cfb-explicit-receiving-v1",
            }
            if (set(row) != set((*ROW_FIELDS, *SOURCE_FIELDS))
                    or str(row["athlete_id"]) != payload["player_id"]
                    or not season-2 <= row["season"] <= season
                    or not date.fromisoformat(row["game_date"]) < cutoff
                    or type(row[column]) is not int or abs(row[column]) > 10000
                    or row["history_policy_version"] != provider_policy.get(row["source_provider"])
                    or not re.fullmatch(r"[0-9a-f]{64}", row["source_sha256"])
                    or not re.fullmatch(r"[0-9a-f]{64}", row["source_record_sha256"])
                    or utc_timestamp(row["source_observed_at"]) > observed_before
                    or stat_row_sha256("cfb", row) != row["source_record_sha256"]):
                raise ValueError("invalid_history")
        values = [row[column] for row in rows]
        over = (sum(value > line for value in values) + .5) / (len(rows)+1)
        expected = over if payload["direction"] == "over" else 1-over
        if (payload["model_sample_size"] != len(rows)
                or abs(float(payload["model_probability"])-expected) > 1e-6
                or payload.get("model_mean_stat") is None
                or abs(float(payload["model_mean_stat"])-sum(values)/len(rows)) > .005001):
            raise ValueError("baseline_history_mismatch")
        # Match the existing exploratory cfb_team_context candidate: only the
        # most recent contiguous segment has the player's current role. A new
        # roster with no observed game under that team has no candidate estimate.
        if rows[-1]["team_abbreviation"] != availability["team"]:
            raise ValueError("no_current_team_history")
        boundary = len(rows)-1
        while boundary > 0 and rows[boundary-1]["team_abbreviation"] == availability["team"]:
            boundary -= 1
        current = rows[boundary:]
        if boundary:
            older_over = (sum(row[column] > line for row in rows[:boundary])+.5)/(boundary+1)
            adjusted = (sum(row[column] > line for row in current)
                        + PRIOR_STRENGTH*older_over)/(len(current)+PRIOR_STRENGTH)
        else:
            adjusted = over
        result.update(status="predicted",
            probability=adjusted if payload["direction"] == "over" else 1-adjusted,
            pooled_probability=expected, prior_strength=PRIOR_STRENGTH,
            current_team=availability["team"], current_team_games=len(current),
            other_team_games=boundary, sample_size=len(rows),
            offer_sha256=offer_digest(payload),
            availability_sha256=digest(availability), inputs=_pack(rows))
        result["record_sha256"] = digest(result)
    except (KeyError, TypeError, ValueError, ArithmeticError, OverflowError) as exc:
        result.update(status="unavailable",
            reason=str(exc) if str(exc) in REASONS else "invalid_shadow_input")
    return result


def verified_shadow_probability(payload: dict) -> float | None:
    try:
        record = payload["cfb_team_role_shadow"]
        if record.get("model_version") != VERSION or record.get("status") != "predicted":
            return None
        expected = shadow_record(payload, _unpack(record["inputs"]))
        return record["probability"] if digest(expected) == digest(record) else None
    except Exception:
        return None


def verified_recorded_shadow_probability(
    raw_payload: str, recorded_at: str | datetime, payload_sha256: str,
) -> float | None:
    """Verify the database-owned immutable prediction receipt, then replay."""
    from sportsbet.ledger import utc_timestamp
    try:
        if (not isinstance(raw_payload, str)
                or hashlib.sha256(raw_payload.encode()).hexdigest() != payload_sha256):
            return None
        payload = json.loads(raw_payload)
        receipt = utc_timestamp(recorded_at)
        if (not utc_timestamp(payload["captured_at"]) <= receipt
                < utc_timestamp(payload["game_start_time"])
                or not 0 <= (receipt-utc_timestamp(payload["quote_time"])).total_seconds() <= 300):
            return None
        return verified_shadow_probability(payload)
    except Exception:
        return None
