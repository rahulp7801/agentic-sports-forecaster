"""Forward-only NFL role shadow with a pinned Jacksonville team alias.

Kalshi uses JAC while nflverse uses JAX. Keep the original v1/v3 code and
receipts untouched so prior pregame decisions remain independently replayable.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
from pathlib import Path

from sportsbet.quant import kalshi_role_shadow as v1
from sportsbet.quant import kalshi_role_shadow_v2 as v3
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.nfl_recent_role_params import SOURCE_SHA256


VERSION = "kalshi-nfl-current-role-shadow-v4"
TEAM_ALIAS_VERSION = "kalshi-jac-nflverse-jax-v1"
COMPARATOR_VERSION = v3.COMPARATOR_VERSION


def _normalize_jacksonville(market_archive: dict, cohort: dict, stats: list[dict],
                            snaps: list[dict]) -> tuple[list[dict], list[dict]]:
    targets = market_archive["evidence"]["sources"]["kalshi"]["targets"]
    aliases = {targets[row["team_target_id"]]["details"]["abbreviation"]
               for row in cohort["selections"]} & {"JAC", "JAX"}
    if aliases == {"JAC", "JAX"}:
        raise ValueError("Conflicting Jacksonville quote aliases")
    if aliases != {"JAC"}:
        return stats, snaps
    # Work on fresh rows only: the manifest still authenticates the original
    # nflverse bytes, and the old model is never patched at module scope.
    def normalize(rows: list[dict]) -> list[dict]:
        return [dict(row, team="JAC") if row.get("team") == "JAX" else row
                for row in rows]
    return normalize(stats), normalize(snaps)


def predict(market_archive: dict, cohort: dict, stats: list[dict],
            snaps: list[dict], identity: dict, *, now: datetime) -> dict:
    stats, snaps = _normalize_jacksonville(market_archive, cohort, stats, snaps)
    report = v1.predict(market_archive, cohort, stats, snaps, identity, now=now)
    report.update(protocol=VERSION, model_version=VERSION,
                  team_alias_version=TEAM_ALIAS_VERSION,
                  implementation_sha256=digest({
                      path.name: hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                      for path in (Path(v1.__file__), Path(__file__))}))
    return report


def build_report(market_archive: dict, cohort: dict, source_dir: Path,
                 manifest: dict, *, now: datetime) -> dict:
    capture = clock(cohort["captured_at"])
    stats, snaps = v3.load_sources(source_dir, capture, manifest)
    identity = v1.identity_index(Path(v1.__file__).with_name("nfl_role_sources.json.gz"), capture)
    report = predict(market_archive, cohort, stats, snaps, identity, now=now)
    normalized_stats, normalized_snaps = _normalize_jacksonville(
        market_archive, cohort, stats, snaps)
    by_player, by_pfr, _ = v1._index(normalized_stats, normalized_snaps)
    offers = {offer["ticker"]: offer for offer in cohort["selections"]}
    targets = market_archive["evidence"]["sources"]["kalshi"]["prop_inventory"]["targets"]
    for forecast in report["forecasts"]:
        offer = offers[forecast["ticker"]]
        matches = identity.get(v1._name(targets[offer["player_target_id"]]["player_name"]), set())
        if len(matches) != 1:
            raise ValueError("Forward comparator identity changed")
        gsis, pfr = next(iter(matches))
        if gsis != forecast["gsis_player_id"] or offer["line"] != forecast["line"]:
            raise ValueError("Forward comparator contract changed")
        history = v1._player_history(gsis, pfr, v1.STAT[offer["prop_type"]],
                                     by_player, by_pfr)
        sample = history[-20:]
        if len(sample) != forecast["sample_games"] or len(sample) != 20:
            raise ValueError("Forward comparator sample changed")
        line = Decimal(str(offer["line"]))
        forecast["prior20_over_probability"] = (
            sum(game["value"] > line for game in sample) + .5) / 21
    report["forecasts_sha256"] = digest(report["forecasts"])
    report.update(comparator_model_version=COMPARATOR_VERSION,
        implementation_sha256=digest({
            path.name: hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for path in (Path(v1.__file__), Path(v3.__file__), Path(__file__))}),
        source_manifest_sha256=digest(manifest), source_manifest=manifest,
        source_sha256={key: item["sha256"] for key, item in manifest["assets"].items()},
        source_assets_prequote=True, crosswalk_sha256=SOURCE_SHA256)
    return report
