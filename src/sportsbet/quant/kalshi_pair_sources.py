"""Stage only the six predeclared free NFL research assets before market capture."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import httpx

from sportsbet.quant.kalshi_role_shadow import MAX_SOURCE_BYTES
from sportsbet.quant import kalshi_role_shadow_v2 as role


ALLOWED_HOSTS = frozenset({
    "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"})


def download_asset(client: httpx.Client, url: str, expected_hash: str) -> bytes:
    target = httpx.URL(url)
    for _ in range(4):
        if (target.scheme != "https" or target.host not in ALLOWED_HOSTS
                or target.port not in (None, 443) or target.userinfo):
            raise ValueError("Untrusted NFL asset location")
        with client.stream("GET", target) as response:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("NFL asset redirect is missing")
                target = target.join(location)
                continue
            response.raise_for_status()
            data = bytearray()
            for block in response.iter_bytes(65536):
                data.extend(block)
                if len(data) > MAX_SOURCE_BYTES:
                    raise ValueError("NFL asset exceeds source size limit")
            raw = bytes(data)
            if not raw or hashlib.sha256(raw).hexdigest() != expected_hash:
                raise ValueError("NFL asset differs from pinned prequote bytes")
            return raw
    raise ValueError("NFL asset exceeded redirect limit")


def stage(root: Path, *, now: datetime, client: httpx.Client) -> dict:
    if now.utcoffset() is None or root.exists() or root.is_symlink():
        raise ValueError("Invalid exclusive NFL source stage")
    releases = {}
    assets = {}
    for kind in role.KINDS:
        tag = "stats_player" if kind == "stats" else "snap_counts"
        response = client.get(
            f"https://api.github.com/repos/nflverse/nflverse-data/releases/tags/{tag}",
            headers={"Accept": "application/vnd.github+json"})
        if response.is_redirect:
            raise ValueError("NFL release metadata redirect is forbidden")
        response.raise_for_status()
        if len(response.content) > role.MAX_RELEASE_BYTES:
            raise ValueError("NFL release metadata exceeds size limit")
        text = response.content.decode("utf-8")
        releases[kind] = dict(text=text, sha256=hashlib.sha256(response.content).hexdigest())
        listing = json.loads(text)
        for year in role.YEARS:
            name = role.filename(kind, year)
            matches = [item for item in listing["assets"] if item.get("name") == name]
            if len(matches) != 1:
                raise ValueError("NFL release asset is missing or ambiguous")
            item, url = matches[0], role.asset_url(kind, year)
            assets[f"{kind}_{year}"] = dict(asset_id=item["id"], filename=name,
                size=item["size"], updated_at=item["updated_at"],
                sha256=item["digest"].removeprefix("sha256:"), url=url)
    manifest = dict(protocol=role.MANIFEST_VERSION, staged_at=now.isoformat(),
                    assets=assets, release_responses=releases)
    role.validate_manifest(manifest, now)
    root.mkdir(parents=True, exist_ok=False)
    for asset in assets.values():
        raw = download_asset(client, asset["url"], asset["sha256"])
        with (root / asset["filename"]).open("xb") as output:
            output.write(raw)
    role.load_sources(root, now, manifest)
    with (root / "source-manifest.json").open("x", encoding="utf-8") as output:
        json.dump(manifest, output, sort_keys=True, indent=2)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            stage(args.output_dir, now=datetime.now(timezone.utc), client=client)
    except (OSError, ValueError, httpx.HTTPError) as exc:
        parser.exit(2, f"Pinned free NFL source staging unavailable ({type(exc).__name__})\n")
    print("Staged 6 hash-pinned free NFL source assets for a private pregame audit")


if __name__ == "__main__":
    main()
