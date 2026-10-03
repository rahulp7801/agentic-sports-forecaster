"""Bound a local recovery capture clock against two independent public clocks.

An HTTP Date check is prospective evidence only. It cannot validate an older
capture retroactively and does not make displayed quotes executable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import uuid

import httpx

VERSION = 'public-http-clock-check-v1'
HOSTS = ('api.github.com', 'www.cloudflare.com')
PATHS = ('/zen', '/cdn-cgi/trace')
MAX_RTT_SECONDS = 2
MAX_OFFSET_SECONDS = 2
MAX_BETWEEN_HOST_OFFSETS_SECONDS = 1.5


def observation(host: str, headers: dict, before: datetime, after: datetime,
                status: int) -> dict:
    """Fail closed on cached or slow HTTP-date evidence."""
    if (host not in HOSTS or before.utcoffset() is None or after.utcoffset() is None
            or status != 200 or not before <= after):
        raise ValueError('Clock response identity, status, or chronology invalid')
    rtt = (after-before).total_seconds()
    if not 0 <= rtt <= MAX_RTT_SECONDS:
        raise ValueError('Clock request exceeded time bound')
    raw_date = headers.get('date')
    if not isinstance(raw_date, str):
        raise ValueError('Independent server Date missing')
    try:
        server = parsedate_to_datetime(raw_date)
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError('Independent server Date invalid') from exc
    if server.utcoffset() is None:
        raise ValueError('Independent server Date has no timezone')
    age = headers.get('age')
    if not (age is None or (type(age) is str and age == '0')
            or (type(age) is int and age == 0)):
        raise ValueError('Cached clock response unavailable')
    midpoint = before + (after-before)/2
    offset = (server-midpoint).total_seconds()
    if not math.isfinite(offset) or abs(offset) > MAX_OFFSET_SECONDS:
        raise ValueError('Local clock differs from independent server')
    return dict(host=host, request_started_at=before.isoformat(),
                response_received_at=after.isoformat(),
                server_date=server.isoformat(), rtt_seconds=rtt,
                server_minus_local_seconds=offset, age=age,
                http_status=status)


async def attest(*, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """Two bounded unsigned, no-cache GETs before a local market read."""
    observations = []
    async with httpx.AsyncClient(timeout=MAX_RTT_SECONDS,
                                 follow_redirects=False, trust_env=False,
                                 transport=transport) as client:
        for host, path in zip(HOSTS, PATHS):
            url = f'https://{host}{path}?clock_nonce={uuid.uuid4().hex}'
            before = datetime.now(timezone.utc)
            async with client.stream('GET', url,
                    headers={'Cache-Control': 'no-cache, no-store'}) as response:
                after = datetime.now(timezone.utc)
                observations.append(observation(
                    host, response.headers, before, after, response.status_code))
    offsets = [item['server_minus_local_seconds'] for item in observations]
    if abs(offsets[0]-offsets[1]) > MAX_BETWEEN_HOST_OFFSETS_SECONDS:
        raise ValueError('Independent server clocks disagree')
    return dict(protocol=VERSION, checked_at=datetime.now(timezone.utc).isoformat(),
                observations=observations, local_clock_acceptable=True)
