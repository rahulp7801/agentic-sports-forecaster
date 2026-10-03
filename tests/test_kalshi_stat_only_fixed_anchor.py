"""The one-shot pregame proof must refuse incomplete or late local evidence."""
from datetime import datetime, timezone
import hashlib
import json

import pytest

from sportsbet.quant import kalshi_stat_only_fixed_anchor as fixed


STAMP = "20261005T0020"
BEFORE = datetime(2026, 10, 4, 23, 9, tzinfo=timezone.utc)


def _receipts(root):
    names = (
        f"stat-only-prelock-fees-{STAMP}.json",
        f"stat-only-prelock-fees-{STAMP}-report.json",
        f"stat-only-prelock-{STAMP}.json",
        f"stat-only-prelock-{STAMP}-report.json",
    )
    for name in names:
        (root / name).write_text('{"retained":true}\n', encoding="utf-8")
    return names


def test_fixed_receipts_must_be_complete_bounded_json_and_pregame(tmp_path):
    names = _receipts(tmp_path)
    marker = fixed.anchor(tmp_path, STAMP, now=BEFORE, dry_run=True)
    assert marker["receipt_sha256"] == {
        name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() for name in names
    }
    with pytest.raises(ValueError, match="window closed"):
        fixed.anchor(tmp_path, STAMP, now=datetime(2026, 10, 5, 0, 19, tzinfo=timezone.utc), dry_run=True)
    (tmp_path / names[0]).write_text("not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        fixed.anchor(tmp_path, STAMP, now=BEFORE, dry_run=True)
    (tmp_path / names[0]).unlink()
    with pytest.raises(ValueError, match="missing"):
        fixed.anchor(tmp_path, STAMP, now=BEFORE, dry_run=True)


def test_anchor_requires_clean_exact_remote_before_any_marker_write(tmp_path, monkeypatch):
    _receipts(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs" / "verification").mkdir(parents=True)
    calls = []

    def command(*args):
        calls.append(args)
        if args[1:] == ("branch", "--show-current"):
            return fixed.BRANCH
        if args[1:] == ("status", "--porcelain"):
            return ""
        if args[1:] == ("rev-parse", "HEAD"):
            return "a" * 40
        if args[1] == "ls-remote":
            return "b" * 40 + "\trefs/heads/" + fixed.BRANCH
        raise AssertionError(args)

    monkeypatch.setattr(fixed, "run", command)
    with pytest.raises(ValueError, match="changed remotely"):
        fixed.anchor(tmp_path, STAMP, now=BEFORE)
    assert not list((tmp_path / "docs" / "verification").iterdir())
    assert all(args[1] not in ("add", "commit", "push") for args in calls)


def test_anchor_records_only_hashes_and_preserves_exact_pushed_commit(tmp_path, monkeypatch):
    _receipts(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fixed, "utc_now", lambda: BEFORE)
    (tmp_path / "docs" / "verification").mkdir(parents=True)
    calls = []

    def command(*args):
        calls.append(args)
        if args[1:] == ("branch", "--show-current"):
            return fixed.BRANCH
        if args[1:] == ("status", "--porcelain"):
            return ""
        if args[1:] == ("rev-parse", "HEAD"):
            return ("a" if len([item for item in calls if item[1:] == args[1:]]) == 1 else "b") * 40
        if args[1] == "ls-remote":
            return "a" * 40 + "\trefs/heads/" + fixed.BRANCH
        return ""

    monkeypatch.setattr(fixed, "run", command)
    marker = fixed.anchor(tmp_path, STAMP, now=BEFORE)
    assert marker["private_commit_oid"] == "b" * 40
    saved = json.loads((tmp_path / "docs" / "verification" / f"{STAMP}-fixed-prelock-anchor.json").read_text())
    assert saved["receipt_sha256"] == marker["receipt_sha256"]
    assert [item for item in calls if item[1] == "push"] == [
        ("git", "push", f"--force-with-lease=refs/heads/{fixed.BRANCH}:{'a' * 40}",
         "origin", f"HEAD:refs/heads/{fixed.BRANCH}"),
        ("git", "push", "origin", f"HEAD:refs/heads/research/fixed-prelock-{STAMP}-anchor"),
    ]
