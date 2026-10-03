"""Reject a push unless its exact GitHub destination is private and owner-only.

Used by the dedicated research checkout's local pre-push hook. This reads
metadata only; it never changes repository settings or publishes evidence.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable


REPOSITORY = "rahulp7801/agentic-sports-forecaster"
REPOSITORY_ID = 1199906339
OWNER = "rahulp7801"
OWNER_ID = 76501505
DESTINATIONS = frozenset(
    prefix + REPOSITORY + suffix
    for prefix in ("https://github.com/", "git@github.com:", "ssh://git@github.com/")
    for suffix in ("", ".git")
)
MAX_METADATA_CHARS = 250_000


def verify_transport() -> None:
    """A Git URL rewrite must not redirect an approved-looking destination."""
    try:
        result = subprocess.run(
            ["git", "config", "--get-regexp", r"^url\..*\.(insteadof|pushinsteadof)$"],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Git destination configuration unavailable") from exc
    if result.returncode != 1 or result.stdout or result.stderr:
        raise ValueError("Git destination rewrites or unavailable configuration block publication")


def github_json(endpoint: str) -> object:
    try:
        result = subprocess.run(
            ["gh", "api", "--hostname", "github.com", "--method", "GET", endpoint],
            capture_output=True, text=True, timeout=20, check=False,
        )
        if result.returncode or not 0 < len(result.stdout) <= MAX_METADATA_CHARS:
            raise ValueError
        return json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        # Provider errors and response bodies may contain sensitive details.
        raise ValueError("GitHub privacy metadata unavailable; no push allowed") from exc


def verify_repository(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("Repository identity or private visibility is not verified")
    owner = value.get("owner")
    permissions = value.get("permissions")
    if (
        type(value.get("id")) is not int or value["id"] != REPOSITORY_ID
        or value.get("full_name") != REPOSITORY
        or value.get("private") is not True or value.get("visibility") != "private"
        or value.get("archived") is not False or value.get("disabled") is not False
        or not isinstance(owner, dict) or type(owner.get("id")) is not int
        or owner["id"] != OWNER_ID or owner.get("login") != OWNER
        or not isinstance(permissions, dict) or permissions.get("admin") is not True
    ):
        raise ValueError("Repository identity or private visibility is not verified")


def verify_access(collaborators: object, invitations: object) -> None:
    if not isinstance(collaborators, list) or len(collaborators) != 1:
        raise ValueError("Owner-only repository access is not verified")
    owner = collaborators[0]
    if (
        not isinstance(owner, dict) or type(owner.get("id")) is not int
        or owner["id"] != OWNER_ID or owner.get("login") != OWNER
        or not isinstance(owner.get("permissions"), dict)
        or owner["permissions"].get("admin") is not True
        or not isinstance(invitations, list) or invitations
    ):
        raise ValueError("Owner-only repository access is not verified")


def guard(destination: str, read: Callable[[str], object] = github_json) -> None:
    if destination not in DESTINATIONS:
        raise ValueError("Push destination is not the approved private repository")
    endpoint = "repos/" + REPOSITORY
    verify_repository(read(endpoint))
    # If a page contains fewer than 100 entries, it is the complete list. Any
    # additional collaborator or any invitation already rejects the push.
    collaborators = read(endpoint + "/collaborators?affiliation=all&per_page=100")
    invitations = read(endpoint + "/invitations?per_page=100")
    verify_access(collaborators, invitations)


def main(arguments: list[str] | None = None) -> int:
    args = sys.argv[1:] if arguments is None else arguments
    try:
        if len(args) != 2:
            raise ValueError("Expected Git pre-push remote name and destination")
        verify_transport()
        guard(args[1])
    except ValueError as exc:
        print("Private publication blocked: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
