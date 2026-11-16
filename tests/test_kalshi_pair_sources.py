"""The private source stage does not trust redirects or changed release bytes."""
import hashlib
import sys
from contextlib import nullcontext

import httpx
import pytest

from sportsbet.quant import kalshi_pair_sources as sources
from sportsbet.quant.kalshi_pair_sources import download_asset


URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/x.parquet"
CANARY = "synthetic-private-http-diagnostic-canary"


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


def _failed_cli(monkeypatch, tmp_path, capsys, error):
    client = object()
    monkeypatch.setattr(sources.httpx, "Client", lambda **kwargs: nullcontext(client))

    def fail_stage(root, *, now, client):
        raise error

    monkeypatch.setattr(sources, "stage", fail_stage)
    monkeypatch.setattr(sys, "argv", ["stage", "--output-dir", str(tmp_path / "sources")])
    with pytest.raises(SystemExit) as stopped:
        sources.main()
    assert stopped.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert CANARY not in captured.err
    assert "example.invalid" not in captured.err
    return captured.err


def _http_failure(status):
    request = httpx.Request("GET", f"https://example.invalid/{CANARY}?token={CANARY}",
                            headers={"Authorization": CANARY})
    response = httpx.Response(503, request=request, content=CANARY,
                             headers={"X-Diagnostic": CANARY})
    response.status_code = status
    return httpx.HTTPStatusError(CANARY, request=request, response=response)


@pytest.mark.parametrize("status", [503, 429])
def test_cli_reports_only_bounded_http_status(monkeypatch, tmp_path, capsys, status):
    message = _failed_cli(monkeypatch, tmp_path, capsys, _http_failure(status))
    assert message == ("Pinned free NFL source staging unavailable (HTTPStatusError)"
                       f" http_status={status}\n")


@pytest.mark.parametrize("error_type", [ValueError, httpx.RequestError])
def test_cli_non_status_failure_keeps_legacy_message(monkeypatch, tmp_path, capsys, error_type):
    error = error_type(CANARY)
    error.response = httpx.Response(503)
    message = _failed_cli(monkeypatch, tmp_path, capsys, error)
    assert message == f"Pinned free NFL source staging unavailable ({error_type.__name__})\n"


@pytest.mark.parametrize("status", [True, 99, 600, CANARY])
def test_cli_does_not_render_invalid_status(monkeypatch, tmp_path, capsys, status):
    message = _failed_cli(monkeypatch, tmp_path, capsys, _http_failure(status))
    assert message == "Pinned free NFL source staging unavailable (HTTPStatusError)\n"
