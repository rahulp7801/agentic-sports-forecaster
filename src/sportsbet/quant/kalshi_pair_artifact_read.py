"""Verify and safely restore a pinned private NFL pair artifact offline.

The expected ZIP SHA256 must have been recorded independently before results.
Neither this reader nor its replay performs a provider request or places bets.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import tempfile
import zipfile

from sportsbet.quant import kalshi_role_shadow as v1
from sportsbet.quant import kalshi_role_shadow_v2 as v3
from sportsbet.quant import kalshi_role_shadow_v4 as v4
from sportsbet.quant.kalshi_ask_policy import freeze as freeze_ask
from sportsbet.quant.kalshi_market_cohort import MAX_ARCHIVE_BYTES, clock
from sportsbet.quant.kalshi_market_settlement import verify_cohort
from sportsbet.quant.kalshi_pair_artifact import (
    MAX_CROSSWALK_BYTES, MAX_TOTAL_BYTES,
)
from sportsbet.quant.kalshi_pair_capture import MAX_PAIR_BYTES, unpack
from sportsbet.quant.kalshi_prior20_ask_policy import freeze as freeze_prior
from sportsbet.quant.nfl_recent_role_params import SOURCE_SHA256


MAX_ZIP_BYTES = MAX_TOTAL_BYTES + 1_000_000
MAX_MANIFEST_BYTES = 100_000
EXPECTED = {
    "pair.json": MAX_PAIR_BYTES,
    "market-archive.json": MAX_ARCHIVE_BYTES,
    "sources/source-manifest.json": v3.MAX_RELEASE_BYTES * 2 + 100_000,
    "sources/nfl_role_sources.json.gz": MAX_CROSSWALK_BYTES,
    "manifest.json": MAX_MANIFEST_BYTES,
    **{f"sources/{v3.filename(kind, year)}": v1.MAX_SOURCE_BYTES
       for kind in v3.KINDS for year in v3.YEARS},
}


def _archive_files(archive_path: Path, expected_sha256: str) -> dict[str, bytes]:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Expected private archive SHA256 is required")
    if (archive_path.is_symlink() or not archive_path.is_file()
            or not 0 < archive_path.stat().st_size <= MAX_ZIP_BYTES):
        raise ValueError("Private archive missing or unbounded")
    raw = archive_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Private archive external SHA256 changed")
    with zipfile.ZipFile(io.BytesIO(raw)) as packed:
        infos = packed.infolist()
        if len(infos) != len(EXPECTED) or {item.filename for item in infos} != set(EXPECTED):
            raise ValueError("Private archive file scope changed")
        if (sum(item.file_size for item in infos) > MAX_TOTAL_BYTES + MAX_MANIFEST_BYTES
                or any(item.is_dir() or item.flag_bits & 1
                       or item.compress_type != zipfile.ZIP_DEFLATED
                       or item.file_size <= 0
                       or item.file_size > EXPECTED[item.filename]
                       or stat.S_ISLNK(item.external_attr >> 16)
                       for item in infos)):
            raise ValueError("Private archive entry is unsafe or unbounded")
        files = {item.filename: packed.read(item) for item in infos}
    manifest = json.loads(files["manifest.json"])
    if set(manifest) != set(EXPECTED) - {"manifest.json"}:
        raise ValueError("Private archive manifest scope changed")
    for name, receipt in manifest.items():
        content = files[name]
        if (not isinstance(receipt, dict)
                or set(receipt) != {"size", "sha256"}
                or receipt["size"] != len(content)
                or hashlib.sha256(content).hexdigest() != receipt["sha256"]):
            raise ValueError("Private archive file integrity changed")
    if hashlib.sha256(files["sources/nfl_role_sources.json.gz"]).hexdigest() != SOURCE_SHA256:
        raise ValueError("Pinned NFL identity crosswalk changed")
    return files


def verify_and_extract(archive_path: Path, expected_sha256: str,
                       output_dir: Path) -> dict:
    """Replay model and policies before writing only allowlisted files."""
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError("Private artifact output already exists")
    files = _archive_files(archive_path, expected_sha256)
    pair = json.loads(files["pair.json"])
    market = json.loads(files["market-archive.json"])
    source_manifest = json.loads(files["sources/source-manifest.json"])
    cohort, shadow = unpack(pair)
    if (shadow["protocol"] not in (v3.VERSION, v4.VERSION)
            or source_manifest != shadow["source_manifest"]
            or pair.get("ask_policy") != freeze_ask(pair)
            or pair.get("prior20_ask_policy") != freeze_prior(pair)):
        raise ValueError("Private pair model or policy receipt changed")
    verify_cohort(market, cohort)
    builder = v3.build_report if shadow["protocol"] == v3.VERSION else v4.build_report
    with tempfile.TemporaryDirectory() as temporary:
        sources = Path(temporary)
        for name in EXPECTED:
            if name.endswith(".parquet"):
                (sources / Path(name).name).write_bytes(files[name])
        if builder(market, cohort, sources, source_manifest,
                   now=clock(shadow["generated_at"])) != shadow:
            raise ValueError("Private pair source or model replay changed")
    output_dir.mkdir(parents=True, exist_ok=False)
    for name, content in files.items():
        path = output_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(content)
    return dict(archive_sha256=expected_sha256,
                selection_sha256=cohort["selection_sha256"],
                forecasts_sha256=shadow["forecasts_sha256"],
                model_version=shadow["protocol"], files=len(files))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True,
                        help="Hash independently recorded before venue results")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify_and_extract(args.archive, args.expected_sha256,
                                    args.output_dir)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        parser.exit(2, f"Private archive cannot be verified ({type(exc).__name__})\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
