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


def test_missing_capture_time_role_receipt_cannot_be_fabricated_by_publisher(tmp_path,monkeypatch):
    root,_=setup_capture(tmp_path,monkeypatch)
    monkeypatch.setattr(publisher,'committed_preflight',lambda *args:({}, {'first_selected_start_at':START}, {}))
    monkeypatch.setattr(publisher.teammate_study,'build',lambda *args,**kwargs:pytest.fail('Context written after missing role receipt'))
    monkeypatch.setattr(publisher,'run',lambda *args:pytest.fail('Dry run mutated Git'))
    with pytest.raises(ValueError,match='Missing'):
        publisher.publish(root,tmp_path/'schedule',now=NOW,dry_run=True)
    assert not (root/'role-weighting.json').exists()
    assert not list((tmp_path/'docs'/'verification').iterdir())


def test_publish_preserves_marker_then_requires_server_proof(tmp_path, monkeypatch):
    root, commitment = setup_capture(tmp_path, monkeypatch)
    monkeypatch.setattr(publisher, "utc_now", lambda: NOW)
    monkeypatch.setattr(publisher, "committed_preflight", lambda *args: ({}, {"first_selected_start_at": START}, {}))
    calls = []
    study_path = publisher.teammate_study.marker_path(root)
    study_marker = {"protocol": "test-study-hash-only"}

    def prepare(*args, **kwargs):
        (root / "teammate-study.json").write_text("{}", encoding="utf-8")
        return study_path, study_marker

    monkeypatch.setattr(publisher.teammate_study, "prepare", prepare)
    role_path = publisher.role_study.marker_path(root)
    role_marker = {'protocol': 'test-role-hash-only'}
    (root / 'role-weighting.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(publisher.role_study, 'prepare', lambda *args: (role_path, role_marker))
    role_proofs = []
    monkeypatch.setattr(publisher.role_study, 'verify_marker', lambda *args: role_proofs.append(args))
    recovery_calls=[]
    def recover(*args):
        assert (root/'remote-anchor.json').exists()
        assert role_proofs and study_proofs
        recovery_calls.append(args)
        return {'status':'local_verified','remote_backed_up':False}
    monkeypatch.setattr(publisher.local_recovery,'best_effort',recover)
    study_proofs = []
    monkeypatch.setattr(publisher.teammate_study, "verify_marker", lambda *args: study_proofs.append(args))

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
        assert json.loads(study_path.read_text()) == study_marker
        assert json.loads(role_path.read_text()) == role_marker
        assert calls[-1] == ("git", "push", "origin", "HEAD:refs/heads/research/next-nfl-stat-only-20261008T1700-anchor")
        return {"remote_pregame_anchor_verified": True, "commit_oid": oid}

    monkeypatch.setattr(publisher, "run", command)
    monkeypatch.setattr(publisher, "verify", verified)
    proof = publisher.publish(root, tmp_path / "schedule", now=NOW)
    assert json.loads((root / "remote-anchor.json").read_text()) == proof
    assert [item for item in calls if item[1] == "push"][0][2] == f"--force-with-lease=refs/heads/{publisher.BRANCH}:{'a' * 40}"
    assert len([item for item in calls if item[1] == "commit"]) == 1
    assert len([item for item in calls if item[1] == "push"]) == 2
    assert study_proofs == [({}, commitment, "b" * 40, "docs/verification/next-nfl-stat-only-20261008T1700-anchor.json")]
    assert role_proofs == study_proofs
    assert recovery_calls == [(root,{'role-weighting':{},'teammate-study':{}},commitment,proof)]
