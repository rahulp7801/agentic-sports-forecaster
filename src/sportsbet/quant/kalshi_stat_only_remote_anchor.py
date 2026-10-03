"""Verify a private PR push anchored a paper commitment before kickoff.

The GitHub PR timeline supplies server-created push time. Git commit author
and committer dates are deliberately ignored because clients can set them.
This module only reads remote metadata and a local commit object.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
import json
from pathlib import Path
import re
import subprocess

from sportsbet.quant.kalshi_market_cohort import clock, digest

VERSION = 'kalshi-nfl-stat-only-remote-anchor-v1'
MARKER_VERSION = 'kalshi-nfl-stat-only-pregame-marker-v1'
OWNER = 'rahulp7801'
REPOSITORY = 'agentic-sports-forecaster'
PR_NUMBER = 345
OID = re.compile(r'[0-9a-f]{40}\Z')
MARKER_PATH = re.compile(r'docs/verification/next-nfl-stat-only-[0-9]{8}T[0-9]{4}-anchor\.json\Z')


def marker(commitment: dict) -> dict:
    return {'protocol': MARKER_VERSION,
            'commitment_sha256': digest(commitment),
            'first_selected_start_at': commitment['first_selected_start_at'],
            'committed_at': commitment['committed_at']}


def _run(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True,
                            timeout=20, check=False)
    if result.returncode or len(result.stdout) > 250_000:
        raise ValueError('Remote anchor evidence unavailable or unbounded')
    return result.stdout


def _timeline(before: str | None) -> dict:
    cursor = 'null' if before is None else json.dumps(before)
    query = (f'query {{ repository(owner:"{OWNER}", name:"{REPOSITORY}") {{ '
             f'pullRequest(number:{PR_NUMBER}) {{ timelineItems(last:100, '
             f'before:{cursor}, itemTypes:[HEAD_REF_FORCE_PUSHED_EVENT]) {{ '
             'pageInfo { hasPreviousPage startCursor } '
             'nodes { ... on HeadRefForcePushedEvent '
             '{ createdAt afterCommit { oid } } } } } } }')
    response = json.loads(_run('gh', 'api', 'graphql', '-f', 'query='+query))
    if response.get('errors') or not isinstance(response.get('data'), dict):
        raise ValueError('GitHub PR timeline query failed')
    page = response['data']['repository']['pullRequest']['timelineItems']
    if not isinstance(page.get('nodes'), list) or not isinstance(page.get('pageInfo'), dict):
        raise ValueError('GitHub PR timeline response malformed')
    return page


def verify(commitment: dict, commit_oid: str, marker_path: str) -> dict:
    if not OID.fullmatch(commit_oid) or not MARKER_PATH.fullmatch(marker_path):
        raise ValueError('Invalid private anchor commit or marker path')
    expected = marker(commitment)
    saved = json.loads(_run('git', 'show', f'{commit_oid}:{marker_path}'))
    if saved != expected:
        raise ValueError('Anchored commit does not contain this pregame commitment')
    first = clock(commitment['first_selected_start_at'])
    generated = clock(commitment['committed_at'])
    before = None
    for _ in range(20):
        page = _timeline(before)
        for event in page['nodes']:
            if event.get('afterCommit', {}).get('oid') != commit_oid:
                continue
            pushed = clock(event['createdAt'])
            if not generated <= pushed+timedelta(seconds=1) or pushed >= first:
                raise ValueError('Private remote push was not pregame')
            return {'protocol': VERSION, 'owner': OWNER, 'repository': REPOSITORY,
                    'pull_request': PR_NUMBER, 'commit_oid': commit_oid,
                    'marker_path': marker_path,
                    'commitment_sha256': expected['commitment_sha256'],
                    'remote_pushed_at': pushed.isoformat(),
                    'first_selected_start_at': first.isoformat(),
                    'remote_pregame_anchor_verified': True}
        if not page['pageInfo']['hasPreviousPage']:
            break
        before = page['pageInfo']['startCursor']
        if not isinstance(before, str) or not before:
            raise ValueError('GitHub PR timeline cursor malformed')
    raise ValueError('No matching server-dated private PR push')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commitment', type=Path, required=True)
    parser.add_argument('--create-marker', action='store_true')
    parser.add_argument('--commit-oid')
    parser.add_argument('--marker-path')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Exclusive remote-anchor report already exists')
    if (args.commitment.is_symlink() or not args.commitment.is_file()
            or not 0 < args.commitment.stat().st_size <= 10_000):
        parser.error('Pregame commitment missing or unbounded')
    commitment = json.loads(args.commitment.read_text(encoding='utf-8'))
    if args.create_marker:
        if (args.commit_oid or args.marker_path
                or not MARKER_PATH.fullmatch(args.output.as_posix())):
            parser.error('Marker creation requires one fixed private tracked path')
        report = marker(commitment)
    else:
        if not args.commit_oid or not args.marker_path:
            parser.error('Verification requires the pushed commit and marker path')
        report = verify(commitment, args.commit_oid, args.marker_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
