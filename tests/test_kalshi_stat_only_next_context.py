"""The prospective context sidecar is pregame, bounded and tamper evident."""
from datetime import datetime, timedelta, timezone
import hashlib
import json

import httpx
import pytest

from sportsbet.quant import kalshi_stat_only_next_context as context


def test_observed_sources_replay_and_changed_bytes_fail(tmp_path, monkeypatch):
    now = datetime(2026, 10, 8, 17, tzinfo=timezone.utc)
    sources = []
    payloads = {}
    for tag in ('injuries', 'weekly_rosters'):
        filename = f'{tag}_2026.parquet'
        url = f'https://github.com/nflverse/nflverse-data/releases/download/{tag}/{filename}'
        body = f'{tag} bytes'.encode()
        payloads[url] = body
        sources.append((tag, filename, url, '0'*64, '2026-10-03T12:00:00+00:00'))
    monkeypatch.setattr(context, 'SOURCES', tuple(sources))

    def respond(request):
        url = str(request.url)
        if url in payloads:
            return httpx.Response(200, content=payloads[url])
        tag = url.rsplit('/', 1)[-1]
        filename = f'{tag}_2026.parquet'
        asset_url = next(item[2] for item in sources if item[0] == tag)
        body = payloads[asset_url]
        listing = {'assets': [{'name': filename, 'state': 'uploaded',
            'id': 42, 'size': len(body), 'browser_download_url': asset_url,
            'digest': 'sha256:'+hashlib.sha256(body).hexdigest(),
            'updated_at': '2026-10-08T16:00:00+00:00'}]}
        return httpx.Response(200, json=listing)

    with httpx.Client(transport=httpx.MockTransport(respond),
                      follow_redirects=False) as client:
        receipt = context.capture(tmp_path/'context', now=now, client=client)
    assert receipt['status'] == 'observed'
    assert context.verify(tmp_path/'context', before=now+timedelta(minutes=1))
    asset = tmp_path/'context/injuries_2026.parquet'
    asset.write_bytes(b'changed')
    with pytest.raises(ValueError, match='bytes changed'):
        context.verify(tmp_path/'context', before=now+timedelta(minutes=1))


def test_missing_public_source_is_explicit_and_pinned(tmp_path, monkeypatch):
    now = datetime(2026, 10, 8, 17, tzinfo=timezone.utc)
    monkeypatch.setattr(context, 'SOURCES', (('injuries', 'x.parquet',
        'https://github.com/nflverse/nflverse-data/releases/download/injuries/x.parquet',
        '0'*64, '2026-10-03T12:00:00+00:00'),))
    with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(503)), follow_redirects=False) as client:
        receipt = context.capture(tmp_path/'context', now=now, client=client)
    assert receipt['status'] == 'unavailable'
    assert receipt['reason'] == 'HTTPStatusError'
    assert context.verify(tmp_path/'context', before=now+timedelta(minutes=1))
    with pytest.raises(ValueError, match='chronology'):
        context.verify(tmp_path/'context', before=now-timedelta(seconds=1))
    path = tmp_path/'context/receipt.json'
    altered = json.loads(path.read_text())
    altered['status'] = 'observed'
    path.write_text(json.dumps(altered))
    with pytest.raises(ValueError):
        context.verify(tmp_path/'context', before=now+timedelta(minutes=1))
