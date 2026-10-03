"""Fail-closed GitHub Actions artifact upload budget for this repository.

Only protects this repository's observed Actions storage. Keep a wide margin for
other repositories, concurrent runs, ZIP wrapping, and delayed API accounting.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen

LIMIT_BYTES = 350_000_000
MAX_CANDIDATE_BYTES = 25_000_000
WRAP_MARGIN_BYTES = 2_000_000


def repository_bytes(repository: str, token: str, opener=urlopen) -> int:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not token:
        raise ValueError("Missing or invalid artifact inventory credentials")
    total = None
    seen = 0
    used = 0
    for page in range(1, 101):
        url = f"https://api.github.com/repos/{repository}/actions/artifacts?per_page=100&page={page}"
        request = Request(url, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "sportsbet-artifact-storage-gate",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        with opener(request, timeout=15) as response:
            payload = json.load(response)
        if not isinstance(payload, dict) or not isinstance(payload.get("total_count"), int) or not isinstance(payload.get("artifacts"), list):
            raise ValueError("Malformed artifact inventory")
        if total is None:
            total = payload["total_count"]
            if total < 0 or total > 10_000:
                raise ValueError("Artifact inventory outside bounded range")
        elif payload["total_count"] != total:
            raise ValueError("Artifact inventory changed during pagination")
        for item in payload["artifacts"]:
            size = item.get("size_in_bytes") if isinstance(item, dict) else None
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise ValueError("Malformed artifact size")
            used += size
        seen += len(payload["artifacts"])
        if seen == total:
            return used
        if seen > total or len(payload["artifacts"]) != 100:
            raise ValueError("Incomplete artifact inventory")
    raise ValueError("Artifact inventory pagination limit reached")


def may_upload(used: int, candidate: int, reserved: int = 0) -> bool:
    return (0 <= used <= LIMIT_BYTES and 0 < candidate <= MAX_CANDIDATE_BYTES
            and 0 <= reserved <= MAX_CANDIDATE_BYTES
            and used + candidate + reserved + WRAP_MARGIN_BYTES <= LIMIT_BYTES)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--reserve-bytes", type=int, default=0,
                        help="Account for another candidate upload in this run")
    args = parser.parse_args()
    retain = False
    reason = "inventory unavailable"
    try:
        candidate = args.candidate.stat().st_size
        used = repository_bytes(os.environ.get("GITHUB_REPOSITORY", ""),
                                os.environ.get("GITHUB_TOKEN", ""))
        retain = may_upload(used, candidate, args.reserve_bytes)
        reason = (f"repo_bytes={used} candidate_bytes={candidate} "
                  f"reserved_bytes={args.reserve_bytes} cap_bytes={LIMIT_BYTES}")
    except (OSError, ValueError, TypeError, KeyError) as error:
        # Do not print API bodies, credentials, or file contents.
        reason = f"storage check failed ({type(error).__name__})"
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"retain={'true' if retain else 'false'}\n")
    print(f"Artifact upload {'allowed' if retain else 'skipped'}: {reason}")


if __name__ == "__main__":
    main()
