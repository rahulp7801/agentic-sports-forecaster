"""Repository drift must reject publication before Git transfers new objects."""
import importlib.util
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("private_push_guard", ROOT / "ops/verify_private_push.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def repository():
    return dict(id=guard.REPOSITORY_ID, full_name=guard.REPOSITORY,
                private=True, visibility="private", archived=False, disabled=False,
                owner=dict(id=guard.OWNER_ID, login=guard.OWNER), permissions=dict(admin=True))


def owner():
    return dict(id=guard.OWNER_ID, login=guard.OWNER, permissions=dict(admin=True))


@pytest.mark.parametrize("destination", sorted(guard.DESTINATIONS))
def test_exact_private_owner_destination_is_allowed(destination):
    calls = []

    def read(endpoint):
        calls.append(endpoint)
        return repository() if len(calls) == 1 else [owner()] if len(calls) == 2 else []

    guard.guard(destination, read)
    assert len(calls) == 3
    assert "affiliation=all" in calls[1]


@pytest.mark.parametrize("destination", [
    "https://github.com/other/agentic-sports-forecaster.git",
    "https://github.com/rahulp7801/other.git",
    "https://github.com.evil.invalid/" + guard.REPOSITORY + ".git",
    "https://user:credential@github.com/" + guard.REPOSITORY + ".git",
    "https://github.com/" + guard.REPOSITORY + ".git?redirect=1",
    "http://github.com/" + guard.REPOSITORY + ".git",
    "file:///private-looking-repository", "", "origin",
])
def test_unexpected_destination_rejected_without_provider_read(destination):
    with pytest.raises(ValueError, match="destination"):
        guard.guard(destination, lambda _: pytest.fail("Unexpected provider read"))


@pytest.mark.parametrize("changes", [
    {"private": False, "visibility": "public"}, {"private": "true"},
    {"visibility": "public"}, {"visibility": "internal"}, {"id": True},
    {"id": guard.REPOSITORY_ID + 1}, {"full_name": "other/repository"},
    {"owner": {"id": guard.OWNER_ID, "login": "lookalike"}},
    {"owner": {"id": guard.OWNER_ID + 1, "login": guard.OWNER}},
    {"permissions": {"admin": False}}, {"archived": True}, {"disabled": True},
])
def test_public_or_ambiguous_metadata_stops_before_access_reads(changes):
    metadata = {**repository(), **changes}
    calls = []

    def read(endpoint):
        calls.append(endpoint)
        return metadata

    with pytest.raises(ValueError, match="private visibility"):
        guard.guard(next(iter(guard.DESTINATIONS)), read)
    assert len(calls) == 1


@pytest.mark.parametrize("metadata", [None, [], {}, {"errors": ["unavailable"]}])
def test_missing_repository_metadata_is_not_permission(metadata):
    with pytest.raises(ValueError, match="identity"):
        guard.verify_repository(metadata)


@pytest.mark.parametrize("collaborators,invitations", [
    ([], []), ([owner(), dict(id=2, login="other")], []),
    ([owner()], [{"id": 1}]), ([owner()], None),
    ({"users": [owner()]}, []), ([{"id": guard.OWNER_ID, "login": guard.OWNER}], []),
    ([{**owner(), "login": "other"}], []), ([{**owner(), "id": True}], []),
])
def test_shared_or_unknown_access_rejects_push(collaborators, invitations):
    with pytest.raises(ValueError, match="Owner-only"):
        guard.verify_access(collaborators, invitations)


@pytest.mark.parametrize("status,stdout", [
    (1, "provider-sensitive-error"), (0, ""), (0, "not-json-secret"),
    (0, "x" * (guard.MAX_METADATA_CHARS + 1)),
], ids=["provider_failure", "empty", "invalid_json", "oversized"])
def test_provider_failure_is_bounded_and_redacted(monkeypatch, status, stdout):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, status, stdout=stdout, stderr="sensitive")

    monkeypatch.setattr(guard.subprocess, "run", run)
    with pytest.raises(ValueError, match="metadata unavailable") as error:
        guard.github_json("repos/" + guard.REPOSITORY)
    assert "sensitive" not in str(error.value)
    assert calls[0][0][2:6] == ["--hostname", "github.com", "--method", "GET"]
    assert calls[0][1]["timeout"] == 20


def test_provider_timeout_rejects_without_leaking_command(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("sensitive", 20)

    monkeypatch.setattr(guard.subprocess, "run", timeout)
    with pytest.raises(ValueError, match="metadata unavailable") as error:
        guard.github_json("repos/" + guard.REPOSITORY)
    assert "sensitive" not in str(error.value)


def test_public_repository_cli_cannot_authorize_hook(monkeypatch, capsys):
    def read(endpoint):
        return {**repository(), "private": False, "visibility": "public"}

    monkeypatch.setattr(guard, "verify_transport", lambda: None)
    monkeypatch.setattr(guard, "guard", lambda destination: original_guard(destination, read))
    assert guard.main(["origin", "https://github.com/" + guard.REPOSITORY + ".git"]) == 1
    assert "Private publication blocked" in capsys.readouterr().err


original_guard = guard.guard


@pytest.mark.parametrize("status,stdout,stderr", [
    (0, "url.file:///other/.insteadof https://github.com/", ""),
    (2, "", "provider-sensitive-error"), (1, "unexpected", ""),
])
def test_destination_rewrite_or_config_failure_is_rejected(monkeypatch, status, stdout, stderr):
    monkeypatch.setattr(guard.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args[0], status, stdout=stdout, stderr=stderr))
    with pytest.raises(ValueError, match="configuration"):
        guard.verify_transport()


def test_absence_of_destination_rewrites_passes(monkeypatch):
    monkeypatch.setattr(guard.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args[0], 1, stdout="", stderr=""))
    guard.verify_transport()


def test_real_git_pre_push_hook_rejects_redirect_before_object_transfer(tmp_path):
    """An approved-looking URL redirected to a local bare fixture cannot pass.

    All Git transport stays on disk; no provider or real remote is contacted.
    """
    bare, source = tmp_path / "bare.git", tmp_path / "source"
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

    def git(*args, cwd=tmp_path, check=True):
        return subprocess.run(["git", *args], cwd=cwd, env=env, check=check,
                              capture_output=True, text=True, timeout=20)

    git("init", "--bare", str(bare))
    git("init", str(source))
    git("config", "user.name", "Guard fixture", cwd=source)
    git("config", "user.email", "fixture@example.invalid", cwd=source)
    (source / "marker.txt").write_text("local fixture\n", encoding="utf-8")
    git("add", "marker.txt", cwd=source)
    git("commit", "-m", "Local guard fixture", cwd=source)
    destination = "https://github.com/" + guard.REPOSITORY + ".git"
    git("remote", "add", "origin", destination, cwd=source)
    git("config", "url." + bare.as_uri() + ".insteadOf", destination, cwd=source)
    hook = source / ".git/hooks/pre-push"
    hook.write_text("#!/bin/sh\nexec " + shlex.quote(Path(sys.executable).as_posix())
                    + " -S " + shlex.quote((ROOT / "ops/verify_private_push.py").as_posix())
                    + ' "$@"\n', encoding="utf-8")
    hook.chmod(0o755)
    rejected = git("-c", "protocol.file.allow=always", "push", "origin", "HEAD",
                   cwd=source, check=False)
    assert rejected.returncode != 0
    assert "Private publication blocked: Git destination rewrites" in rejected.stderr
    assert git("show-ref", cwd=bare, check=False).returncode == 1
    counts = git("count-objects", "-v", cwd=bare).stdout.splitlines()
    assert "count: 0" in counts and "in-pack: 0" in counts
