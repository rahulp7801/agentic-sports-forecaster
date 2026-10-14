"""Replay a completed free paper capture and privately anchor it before kickoff."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys

from sportsbet.quant.kalshi_market_cohort import clock
from sportsbet.quant.kalshi_stat_only_next_eval import _input, committed_preflight
from sportsbet.quant.kalshi_stat_only_remote_anchor import marker, verify
from sportsbet.quant.kalshi_stat_only_fixed_anchor import BRANCH, OID, run
from sportsbet.quant import kalshi_stat_only_next_teammate_study_v2 as teammate_study
from sportsbet.quant import kalshi_role_weighting_study as role_study
from sportsbet.quant import kalshi_paper_local_recovery as local_recovery


ROOT_NAME = re.compile(r"next-nfl-stat-only-(?P<stamp>[0-9]{8}T[0-9]{4})\Z")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def publish(root: Path, schedule: Path, *, now: datetime | None = None,
            dry_run: bool = False) -> dict:
    match = ROOT_NAME.fullmatch(root.name)
    if (match is None or root.is_symlink() or not root.is_dir()
            or root.resolve().parent != (Path.cwd() / ".local").resolve()):
        raise ValueError("Unexpected private paper capture directory")
    commitment, _ = _input(root / "commitment.json", 10_000)
    inputs = {name: str(root / f"{name}.json")
              for name in ("pair", "market", "forecast", "quotes", "decisions", "control")}
    inputs["schedule"] = str(schedule)
    values, pre, _ = committed_preflight(inputs, root / "sources", commitment)
    current = now or utc_now()
    first = clock(pre["first_selected_start_at"])
    if (current.utcoffset() is None or not clock(commitment["committed_at"]) <= current
            or current >= first - timedelta(minutes=2)):
        raise ValueError("Private paper anchor is late or clock invalid")
    saved = marker(commitment)
    if dry_run:
        role_study.prepare(root, values, commitment)
        teammate_study.build(values, root / "sources", commitment, now=current)
        return saved
    if run("git", "branch", "--show-current") != BRANCH or run("git", "status", "--porcelain"):
        raise ValueError("Release checkout is not clean on the expected branch")
    old = run("git", "rev-parse", "HEAD")
    observed = run("git", "ls-remote", "--exit-code", "origin", f"refs/heads/{BRANCH}")
    if not OID.fullmatch(old) or observed != f"{old}\trefs/heads/{BRANCH}":
        raise ValueError("Release branch changed remotely")
    stamp = match["stamp"]
    path = Path("docs/verification") / f"next-nfl-stat-only-{stamp}-anchor.json"
    report_path = root / "remote-anchor.json"
    if path.exists() or path.is_symlink() or report_path.exists() or report_path.is_symlink():
        raise ValueError("Private paper anchor already exists")
    context_path = teammate_study.marker_path(root)
    if context_path.exists() or context_path.is_symlink():
        raise ValueError("Private prospective context anchor already exists")
    role_path, role_marker = role_study.prepare(root, values, commitment)
    if role_path.exists() or role_path.is_symlink():
        raise ValueError("Private prospective role anchor already exists")
    study_path, study_marker = teammate_study.prepare(root, values, commitment, now=current)
    with role_path.open("x", encoding="utf-8") as stream:
        json.dump(role_marker, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    with study_path.open("x", encoding="utf-8") as stream:
        json.dump(study_marker, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    with path.open("x", encoding="utf-8") as stream:
        json.dump(saved, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    run("git", "add", "--", str(path), str(study_path), str(role_path))
    run("git", "diff", "--cached", "--check")
    run("git", "commit", "--amend", "--no-edit")
    new = run("git", "rev-parse", "HEAD")
    if not OID.fullmatch(new) or new == old or utc_now() >= first - timedelta(minutes=1):
        raise ValueError("Private paper push window closed or commit failed")
    run("git", "push", f"--force-with-lease=refs/heads/{BRANCH}:{old}",
        "origin", f"HEAD:refs/heads/{BRANCH}")
    run("git", "push", "origin", f"HEAD:refs/heads/research/next-nfl-stat-only-{stamp}-anchor")
    proof = verify(commitment, new, path.as_posix())
    study_receipt, _ = _input(root / "teammate-study.json", 500_000)
    teammate_study.verify_marker(study_receipt, commitment, new, path.as_posix())
    role_receipt, _ = _input(root / "role-weighting.json", 500_000)
    role_study.verify_marker(role_receipt, commitment, new, path.as_posix())
    with report_path.open("x", encoding="utf-8") as stream:
        json.dump(proof, stream, sort_keys=True, indent=2, allow_nan=False)
    recovery_result=local_recovery.best_effort(root, {**values, 'role-weighting':role_receipt,
        'teammate-study':study_receipt}, commitment, proof)
    if recovery_result['status']!='local_verified':
        print('Local evidence recovery unavailable; original pregame anchor remains verified.',file=sys.stderr)
    return proof


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(publish(args.output_dir, args.schedule, dry_run=args.dry_run), sort_keys=True))


if __name__ == "__main__":
    main()
