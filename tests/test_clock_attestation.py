"""Clock evidence gates for free local recovery captures."""
import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from sportsbet.quant.clock_attestation import attest, observation


def test_clock_observation_accepts_small_uncached_offset():
    start = datetime(2026, 10, 4, 1, 0, 41, tzinfo=timezone.utc)
    result = observation('api.github.com',
        {'date': format_datetime(start, usegmt=True)},
        start, start + timedelta(milliseconds=100), 200)
    assert abs(result['server_minus_local_seconds']) < 1
    assert result['age'] is None
    assert observation('api.github.com',
        {'date': format_datetime(start, usegmt=True), 'age': '0'},
        start, start + timedelta(milliseconds=100), 200)['age'] == '0'


@pytest.mark.parametrize('headers,elapsed', [
    ({'date': 'Sun, 04 Oct 2026 00:59:00 GMT'}, .1),
    ({'date': 'Sun, 04 Oct 2026 01:00:41 GMT', 'age': '5'}, .1),
    ({'date': 'Sun, 04 Oct 2026 01:00:41 GMT', 'age': False}, .1),
    ({'date': 'Sun, 04 Oct 2026 01:00:41 GMT', 'age': '00'}, .1),
    ({'date': 'Sun, 04 Oct 2026 01:00:41 GMT', 'age': 0.0}, .1),
    ({'date': 'Sun, 04 Oct 2026 01:00:41 GMT'}, 3),
    ({}, .1),
])
def test_stale_cached_slow_or_missing_clock_fails(headers, elapsed):
    start = datetime(2026, 10, 4, 1, 0, 41, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        observation('api.github.com', headers,
                    start, start + timedelta(seconds=elapsed), 200)


def test_two_servers_are_required_without_authentication():
    hosts = []
    async def handle(request):
        hosts.append(request.url.host)
        assert request.method == 'GET'
        assert request.headers['cache-control'] == 'no-cache, no-store'
        assert 'clock_nonce=' in str(request.url)
        assert 'authorization' not in request.headers
        return httpx.Response(200, headers={'Date': format_datetime(
            datetime.now(timezone.utc), usegmt=True)})
    result = asyncio.run(attest(transport=httpx.MockTransport(handle)))
    assert hosts == ['api.github.com', 'www.cloudflare.com']
    assert result['local_clock_acceptable'] is True
    assert len(result['observations']) == 2
