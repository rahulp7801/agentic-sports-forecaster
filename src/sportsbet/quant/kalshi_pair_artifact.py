"""Pack a complete private model/market receipt from the normal free run."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from sportsbet.quant.kalshi_market_cohort import MAX_ARCHIVE_BYTES, clock
from sportsbet.quant.kalshi_market_settlement import verify_cohort
from sportsbet.quant.kalshi_pair_capture import MAX_PAIR_BYTES, unpack
from sportsbet.quant import kalshi_role_shadow as v1
from sportsbet.quant import kalshi_role_shadow_v2 as v2
from sportsbet.quant.nfl_recent_role_params import SOURCE_SHA256


MAX_TOTAL_BYTES = 25_000_000
MAX_CROSSWALK_BYTES = 4_000_000
MAX_MARKET_FILES = 128


def bounded(path: Path, maximum: int) -> bytes:
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= maximum):
        raise ValueError("Private artifact input is missing or unbounded")
    return path.read_bytes()


def pack(pair_path: Path, source_dir: Path, market_dir: Path, output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise FileExistsError("Private artifact already exists")
    pair_bytes = bounded(pair_path, MAX_PAIR_BYTES)
    pair = json.loads(pair_bytes)
    cohort, shadow = unpack(pair)
    if shadow["protocol"] != v2.VERSION:
        raise ValueError("Private workflow requires the forward source protocol")
    manifest_bytes = bounded(source_dir/"source-manifest.json", v2.MAX_RELEASE_BYTES*2+100_000)
    manifest = json.loads(manifest_bytes)
    if manifest != shadow["source_manifest"]:
        raise ValueError("Private source manifest does not match frozen shadow")
    matches = []
    market_paths = list(market_dir.glob("*.json"))
    if len(market_paths) > MAX_MARKET_FILES:
        raise ValueError("Private market archive search exceeds its file limit")
    for path in market_paths:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ARCHIVE_BYTES:
            continue
        candidate = json.loads(path.read_text(encoding="utf-8"))
        if (candidate.get("summary", {}).get("evidence_sha256")
                == cohort["market_archive_sha256"]):
            matches.append((path, candidate))
    if len(matches) != 1:
        raise ValueError("Private pair has no unique captured market archive")
    market_path, market = matches[0]
    verify_cohort(market, cohort)
    if v2.build_report(market, cohort, source_dir, manifest,
                       now=clock(shadow["generated_at"])) != shadow:
        raise ValueError("Private pair source or model replay changed")
    inputs = {"pair.json": pair_bytes,
              "market-archive.json": bounded(market_path, MAX_ARCHIVE_BYTES),
              "sources/source-manifest.json": manifest_bytes,
              "sources/nfl_role_sources.json.gz": bounded(
                  Path(v1.__file__).with_name("nfl_role_sources.json.gz"), MAX_CROSSWALK_BYTES)}
    if hashlib.sha256(inputs["sources/nfl_role_sources.json.gz"]).hexdigest() != SOURCE_SHA256:
        raise ValueError("Private crosswalk source changed")
    for asset in manifest["assets"].values():
        inputs[f"sources/{asset['filename']}"] = bounded(
            source_dir/asset["filename"], v1.MAX_SOURCE_BYTES)
    if sum(len(value) for value in inputs.values()) > MAX_TOTAL_BYTES:
        raise ValueError("Private pair artifact exceeds total size limit")
    file_manifest = {name: dict(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                     for name, raw in sorted(inputs.items())}
    inputs["manifest.json"] = (json.dumps(file_manifest, sort_keys=True,
                                           separators=(",", ":"))+"\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as target:
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6) as archive:
            for name, raw in sorted(inputs.items()):
                archive.writestr(name, raw)
    return dict(files=len(inputs), bytes=output.stat().st_size,
                selection_sha256=cohort["selection_sha256"],
                forecasts_sha256=shadow["forecasts_sha256"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--market-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = pack(args.pair, args.source_dir, args.market_dir, args.output)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Private paired evidence unavailable ({type(exc).__name__})\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
