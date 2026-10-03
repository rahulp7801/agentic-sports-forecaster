"""Client-controlled Git dates cannot substitute for a server-dated PR push."""
import json

import pytest

from sportsbet.quant import kalshi_stat_only_remote_anchor as anchor


OID = 'a'*40
PATH = 'docs/verification/next-nfl-stat-only-20261008T1700-anchor.json'
REF = 'refs/heads/research/next-nfl-stat-only-20261008T1700-anchor'
COMMITMENT = {'committed_at': '2026-10-08T17:01:00+00:00',
              'first_selected_start_at': '2026-10-09T00:15:00+00:00'}


def test_server_push_and_exact_commit_blob_prove_pregame_anchor(monkeypatch):
    calls = []
    def run(*args):
        if args[:2] == ('git', 'show'):
            return json.dumps(anchor.marker(COMMITMENT))
        assert args[:4] == ('git', 'ls-remote', '--exit-code', '--refs')
        assert args[-1] == REF
        return f'{OID}\t{REF}\n'
    monkeypatch.setattr(anchor, '_run', run)

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
    assert report['preservation_ref'] == REF
    assert report['protocol'] == anchor.VERSION


def test_preservation_ref_must_point_at_exact_pregame_commit(monkeypatch):
    monkeypatch.setattr(anchor, '_run', lambda *args: f"{'b'*40}\t{REF}\n")
    with pytest.raises(ValueError, match='not preserved'):
        anchor._preserved(OID, PATH)
    monkeypatch.setattr(anchor, '_run', lambda *args: '')
    with pytest.raises(ValueError, match='not preserved'):
        anchor._preserved(OID, PATH)


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
