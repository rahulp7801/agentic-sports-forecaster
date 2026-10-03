"""Privately anchor a fixed paper cohort's later free price receipts before kickoff.

This one-shot helper is for the two already scheduled October 5/6 observations.
It never requests a quote or result. A clean release checkout is required so
the only new tracked bytes are the four receipt hashes in the marker.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess


BRANCH = "release/20261003-consumer-context"
COHORTS = {
    "20261005T0020": "2026-10-05T00:20:00+00:00",
    "20261006T0015": "2026-10-06T00:15:00+00:00",
}
MAX_RECEIPT_BYTES = 5_000_000
OID = re.compile(r"[0-9a-f]{40}\Z")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def receipt_hashes(root: Path, stamp: str) -> dict[str, str]:
    """Hash only the fixed bounded JSON receipts; refuse a partial capture."""
    names = (
        f"stat-only-prelock-fees-{stamp}.json",
        f"stat-only-prelock-fees-{stamp}-report.json",
        f"stat-only-prelock-{stamp}.json",
        f"stat-only-prelock-{stamp}-report.json",
    )
    hashes: dict[str, str] = {}
    for name in names:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Fixed receipt missing: {name}")
        size = path.stat().st_size
        if not 0 < size <= MAX_RECEIPT_BYTES:
            raise ValueError(f"Fixed receipt size invalid: {name}")
        raw = path.read_bytes()
        json.loads(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    return hashes


def run(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True,
                            timeout=25, check=False)
    if result.returncode:
        raise ValueError(f"Command failed: {args[0]} {args[1]}")
    return result.stdout.strip()


def anchor(root: Path, stamp: str, *, now: datetime | None = None,
           dry_run: bool = False) -> dict:
    if stamp not in COHORTS:
        raise ValueError("Unrecognized fixed paper kickoff")
    current = now or utc_now()
    kickoff = datetime.fromisoformat(COHORTS[stamp])
    if current.tzinfo is None or current >= kickoff - timedelta(minutes=2):
        raise ValueError("Pregame remote anchor window closed")
    hashes = receipt_hashes(root, stamp)
    marker = {
        "protocol": "kalshi-fixed-prelock-private-anchor-v1",
        "kickoff": COHORTS[stamp],
        "local_hashed_at": current.astimezone(timezone.utc).isoformat(),
        "receipt_sha256": hashes,
    }
    if dry_run:
        return marker

    if run("git", "branch", "--show-current") != BRANCH or run("git", "status", "--porcelain"):
        raise ValueError("Release checkout is not clean on the expected branch")
    old = run("git", "rev-parse", "HEAD")
    remote = run("git", "ls-remote", "--exit-code", "origin", f"refs/heads/{BRANCH}")
    if not OID.fullmatch(old) or remote != f"{old}\trefs/heads/{BRANCH}":
        raise ValueError("Release branch changed remotely")
    path = Path("docs/verification") / f"{stamp}-fixed-prelock-anchor.json"
    if path.exists() or path.is_symlink():
        raise ValueError("Fixed prelock marker already exists")
    path.write_text(json.dumps(marker, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    run("git", "add", "--", str(path))
    run("git", "diff", "--cached", "--check")
    run("git", "commit", "--amend", "--no-edit")
    new = run("git", "rev-parse", "HEAD")
    if not OID.fullmatch(new) or new == old:
        raise ValueError("Fixed marker commit failed")
    if utc_now() >= kickoff - timedelta(minutes=1):
        raise ValueError("Pregame push window closed")
    run("git", "push", f"--force-with-lease=refs/heads/{BRANCH}:{old}",
        "origin", f"HEAD:refs/heads/{BRANCH}")
    run("git", "push", "origin", f"HEAD:refs/heads/research/fixed-prelock-{stamp}-anchor")
    marker["private_commit_oid"] = new
    return marker


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--stamp", choices=COHORTS, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(anchor(args.evidence_root, args.stamp, dry_run=args.dry_run), sort_keys=True))


if __name__ == "__main__":
    main()
