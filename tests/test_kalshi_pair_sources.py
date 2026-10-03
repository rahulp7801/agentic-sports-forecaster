"""The private source stage does not trust redirects or changed release bytes."""
import hashlib

import httpx
import pytest

from sportsbet.quant.kalshi_pair_sources import download_asset


URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/x.parquet"


def test_only_hash_pinned_release_bytes_are_accepted():
    raw = b"fixture parquet bytes"
    expected = hashlib.sha256(raw).hexdigest()
    def respond(request):
        if request.url.host == "github.com":
            return httpx.Response(302, headers={"location":
                "https://release-assets.githubusercontent.com/fixture"})
        return httpx.Response(200, content=raw)
    with httpx.Client(transport=httpx.MockTransport(respond),
                      follow_redirects=False) as client:
        assert download_asset(client, URL, expected) == raw
        with pytest.raises(ValueError, match="pinned"):
            download_asset(client, URL, "0"*64)


def test_untrusted_redirect_is_rejected_before_request():
    calls=[]
    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://example.com/secret"})
    with httpx.Client(transport=httpx.MockTransport(respond),
                      follow_redirects=False) as client:
        with pytest.raises(ValueError, match="Untrusted"):
            download_asset(client, URL, "0"*64)
    assert len(calls) == 1
