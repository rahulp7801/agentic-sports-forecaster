"""Client-controlled Git dates cannot substitute for a server-dated PR push."""
import json

import pytest

from sportsbet.quant import kalshi_stat_only_remote_anchor as anchor


OID = 'a'*40
PATH = 'docs/verification/next-nfl-stat-only-20261008T1700-anchor.json'
COMMITMENT = {'committed_at': '2026-10-08T17:01:00+00:00',
              'first_selected_start_at': '2026-10-09T00:15:00+00:00'}


def test_server_push_and_exact_commit_blob_prove_pregame_anchor(monkeypatch):
    calls = []
    monkeypatch.setattr(anchor, '_run', lambda *args: json.dumps(anchor.marker(COMMITMENT)))

    def page(before):
        calls.append(before)
        if before is None:
            return {'nodes': [], 'pageInfo': {'hasPreviousPage': True,
                                              'startCursor': 'older'}}
        return {'nodes': [{'afterCommit': {'oid': OID},
                           'createdAt': '2026-10-08T17:02:00Z'}],
                'pageInfo': {'hasPreviousPage': False, 'startCursor': None}}

    monkeypatch.setattr(anchor, '_timeline', page)
    report = anchor.verify(COMMITMENT, OID, PATH)
    assert calls == [None, 'older']
    assert report['remote_pregame_anchor_verified']
    assert report['commitment_sha256'] == anchor.digest(COMMITMENT)


def test_late_push_and_changed_commitment_fail(monkeypatch):
    monkeypatch.setattr(anchor, '_run', lambda *args: json.dumps(anchor.marker(COMMITMENT)))
    monkeypatch.setattr(anchor, '_timeline', lambda before: {
        'nodes': [{'afterCommit': {'oid': OID},
                   'createdAt': '2026-10-09T00:15:00Z'}],
        'pageInfo': {'hasPreviousPage': False, 'startCursor': None}})
    with pytest.raises(ValueError, match='not pregame'):
        anchor.verify(COMMITMENT, OID, PATH)
    changed = dict(COMMITMENT, committed_at='2026-10-08T17:02:00+00:00')
    with pytest.raises(ValueError, match='does not contain'):
        anchor.verify(changed, OID, PATH)
