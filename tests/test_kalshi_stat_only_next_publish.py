"""Only a fully replayed pregame capture may be published and preserved."""
from datetime import datetime, timezone
import json

import pytest

from sportsbet.quant import kalshi_stat_only_next_publish as publisher
from sportsbet.quant.kalshi_stat_only_remote_anchor import marker


NOW = datetime(2026, 10, 8, 17, 25, tzinfo=timezone.utc)
START = "2026-10-09T00:15:00+00:00"


def setup_capture(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / ".local" / "next-nfl-stat-only-20261008T1700"
    root.mkdir(parents=True)
    (tmp_path / "docs" / "verification").mkdir(parents=True)
    commitment = {"committed_at": "2026-10-08T17:04:00+00:00",
                  "first_selected_start_at": START, "input_sha256": {"pair": "a" * 64}}
    (root / "commitment.json").write_text(json.dumps(commitment), encoding="utf-8")
    return root, commitment


def test_failed_source_replay_cannot_write_marker_or_push(tmp_path, monkeypatch):
    root, _ = setup_capture(tmp_path, monkeypatch)

    def changed(*args):
        raise ValueError("Pregame input hash changed")

    monkeypatch.setattr(publisher, "committed_preflight", changed)
    monkeypatch.setattr(publisher, "run", lambda *args: pytest.fail("Git called before replay"))
    with pytest.raises(ValueError, match="hash changed"):
        publisher.publish(root, tmp_path / "schedule", now=NOW)
    assert not list((tmp_path / "docs" / "verification").iterdir())


def test_late_capture_cannot_publish_even_after_replay(tmp_path, monkeypatch):
    root, _ = setup_capture(tmp_path, monkeypatch)
    monkeypatch.setattr(publisher, "committed_preflight", lambda *args: ({}, {"first_selected_start_at": START}, {}))
    monkeypatch.setattr(publisher, "run", lambda *args: pytest.fail("Late anchor called Git"))
    with pytest.raises(ValueError, match="late"):
        publisher.publish(root, tmp_path / "schedule", now=datetime(2026, 10, 9, 0, 14, tzinfo=timezone.utc))


def test_publish_preserves_marker_then_requires_server_proof(tmp_path, monkeypatch):
    root, commitment = setup_capture(tmp_path, monkeypatch)
    monkeypatch.setattr(publisher, "utc_now", lambda: NOW)
    monkeypatch.setattr(publisher, "committed_preflight", lambda *args: ({}, {"first_selected_start_at": START}, {}))
    calls = []

    def command(*args):
        calls.append(args)
        if args[1] == "branch":
            return publisher.BRANCH
        if args[1] == "status":
            return ""
        if args[1] == "rev-parse":
            return ("a" if sum(item[1] == "rev-parse" for item in calls) == 1 else "b") * 40
        if args[1] == "ls-remote":
            return "a" * 40 + "\trefs/heads/" + publisher.BRANCH
        return ""

    def verified(value, oid, path):
        assert value == commitment and oid == "b" * 40
        assert json.loads((tmp_path / path).read_text()) == marker(commitment)
        assert calls[-1] == ("git", "push", "origin", "HEAD:refs/heads/research/next-nfl-stat-only-20261008T1700-anchor")
        return {"remote_pregame_anchor_verified": True, "commit_oid": oid}

    monkeypatch.setattr(publisher, "run", command)
    monkeypatch.setattr(publisher, "verify", verified)
    proof = publisher.publish(root, tmp_path / "schedule", now=NOW)
    assert json.loads((root / "remote-anchor.json").read_text()) == proof
    assert [item for item in calls if item[1] == "push"][0][2] == f"--force-with-lease=refs/heads/{publisher.BRANCH}:{'a' * 40}"
