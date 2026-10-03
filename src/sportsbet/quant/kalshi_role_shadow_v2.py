"""Forward-only NFL role shadow with a per-capture free-source manifest.

The October 3 v1 shadow remains frozen and replayable with its original six
assets. This version can follow official releases without rewriting v1.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant import kalshi_role_shadow as v1
from sportsbet.quant.nfl_recent_role_params import SOURCE_SHA256


VERSION = "kalshi-nfl-current-role-shadow-v3"
MANIFEST_VERSION = "kalshi-nfl-source-manifest-v2"
COMPARATOR_VERSION = "kalshi-nfl-prior20-jeffreys-v1"
KINDS = ("stats", "snaps")
YEARS = (2024, 2025, 2026)
MAX_RELEASE_BYTES = 1_000_000


def filename(kind: str, year: int) -> str:
    if kind not in KINDS or year not in YEARS:
        raise ValueError("Unexpected NFL asset")
    return (f"stats_player_week_{year}.parquet" if kind == "stats"
            else f"snap_counts_{year}.parquet")


def asset_url(kind: str, year: int) -> str:
    tag = "stats_player" if kind == "stats" else "snap_counts"
    return (f"https://github.com/nflverse/nflverse-data/releases/download/"
            f"{tag}/{filename(kind, year)}")


def validate_manifest(manifest: dict, capture: datetime) -> dict:
    if (not isinstance(manifest, dict) or manifest.get("protocol") != MANIFEST_VERSION
            or clock(manifest["staged_at"]) > capture):
        raise ValueError("NFL source manifest chronology failed")
    assets, releases = manifest["assets"], manifest["release_responses"]
    if (set(assets) != {f"{kind}_{year}" for kind in KINDS for year in YEARS}
            or set(releases) != set(KINDS)):
        raise ValueError("NFL source manifest scope failed")
    for kind in KINDS:
        response = releases[kind]
        text = response["text"]
        if (not isinstance(text, str) or len(text.encode()) > MAX_RELEASE_BYTES
                or hashlib.sha256(text.encode()).hexdigest() != response["sha256"]):
            raise ValueError("NFL release metadata integrity failed")
        listing = json.loads(text)
        expected = {filename(kind, year): assets[f"{kind}_{year}"] for year in YEARS}
        for name, chosen in expected.items():
            matches = [item for item in listing["assets"] if item.get("name") == name]
            if len(matches) != 1:
                raise ValueError("NFL release asset identity failed")
            official, year = matches[0], int(name.rsplit("_", 1)[1].split(".")[0])
            expected_fields = dict(asset_id=official["id"], filename=name,
                size=official["size"], updated_at=official["updated_at"],
                sha256=official["digest"].removeprefix("sha256:"),
                url=asset_url(kind, year))
            if (chosen != expected_fields or not isinstance(chosen["asset_id"], int)
                    or not 0 < chosen["size"] <= v1.MAX_SOURCE_BYTES
                    or re.fullmatch(r"[0-9a-f]{64}", chosen["sha256"]) is None
                    or clock(chosen["updated_at"]) > clock(manifest["staged_at"])
                    or clock(chosen["updated_at"]) > capture):
                raise ValueError("NFL release asset chronology or hash failed")
    return assets


def load_sources(root: Path, capture: datetime, manifest: dict) -> tuple[list[dict], list[dict]]:
    import polars as pl

    assets = validate_manifest(manifest, capture)
    stats, snaps = [], []
    for kind in KINDS:
        for year in YEARS:
            asset = assets[f"{kind}_{year}"]
            path = root / asset["filename"]
            if (path.is_symlink() or not path.is_file()
                    or path.stat().st_size != asset["size"]
                    or hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]):
                raise ValueError("Pinned NFL source file missing or changed")
            columns = v1.STATS_COLUMNS if kind == "stats" else v1.SNAP_COLUMNS
            frame = pl.read_parquet(path).select(columns).filter(pl.col("season") == year)
            if kind == "stats":
                stats.extend(frame.filter(pl.col("season_type") == "REG").to_dicts())
            else:
                snaps.extend(frame.filter(pl.col("week") <= 18).to_dicts())
    return stats, snaps


def build_report(market_archive: dict, cohort: dict, source_dir: Path,
                 manifest: dict, *, now: datetime) -> dict:
    capture = clock(cohort["captured_at"])
    stats, snaps = load_sources(source_dir, capture, manifest)
    identity = v1.identity_index(Path(v1.__file__).with_name("nfl_role_sources.json.gz"), capture)
    report = v1.predict(market_archive, cohort, stats, snaps, identity, now=now)
    by_player, by_pfr, _ = v1._index(stats, snaps)
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
    report.update(protocol=VERSION, model_version=VERSION,
        comparator_model_version=COMPARATOR_VERSION,
        implementation_sha256=digest({
            path.name: hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for path in (Path(v1.__file__), Path(__file__))}),
        source_manifest_sha256=digest(manifest), source_manifest=manifest,
        source_sha256={key: item["sha256"] for key, item in manifest["assets"].items()},
        source_assets_prequote=True, crosswalk_sha256=SOURCE_SHA256)
    return report
