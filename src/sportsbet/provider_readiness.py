"""Read-only provider observations; never authorize or perform quote collection."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import ipaddress
import json
import logging
import os
import re
from urllib.parse import urlsplit

import httpx

from sportsbet.ingestion.odds_api_credential import require_safe_odds_api_key


SPORTS_URL = 'https://api.the-odds-api.com/v4/sports/'
SPORT_KEYS = {'nfl': 'americanfootball_nfl', 'nba': 'basketball_nba',
              'cfb': 'americanfootball_ncaaf'}
MAX_RESPONSE_BYTES = 256 * 1024
MAX_SAFE_INTEGER = 2**53 - 1
USAGE_QUERY = ('SELECT risk_day, credits FROM api_usage '
               'WHERE risk_day>=? AND risk_day<=? ORDER BY risk_day')


class _ProviderUnavailable(Exception):
    def __init__(self, reason: str, http_status: int | None = None):
        if reason not in {'http_status', 'invalid_headers', 'nonzero_request_cost',
                          'invalid_body', 'response_too_large'}:
            raise ValueError('Invalid diagnostic reason')
        super().__init__()
        self.reason = reason
        self.http_status = (http_status if type(http_status) is int
                            and 200 <= http_status <= 599 else None)


def _base_report(now: datetime | None) -> dict:
    clock = (now.astimezone(timezone.utc) if isinstance(now, datetime)
             and now.utcoffset() is not None else datetime.now(timezone.utc))
    return dict(schema_version=1, status='unavailable', captured_at=clock.isoformat(),
                credential=dict(status='not_checked'), local_budget=dict(status='not_checked'),
                provider=dict(status='not_checked'), activation_authorized=False,
                free_plan_verified=False, reserve_not_evaluated=True)


def _hosted_url(value: str | None) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError('Explicit hosted analytics source required')
    parsed = urlsplit(value)
    host = parsed.hostname
    if (parsed.scheme not in ('postgresql', 'postgres', 'postgresql+psycopg')
            or not host or parsed.fragment or host.lower() == 'localhost'
            or host.lower().endswith('.localhost')):
        raise ValueError('Explicit hosted analytics source required')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if address.is_loopback or address.is_unspecified:
            raise ValueError('Explicit hosted analytics source required')
    return value


def _read_only_ledger(database_url: str):
    # This class skips schema initialization and forces a read-only transaction.
    from sportsbet.quant.audit_storage import ReadOnlyLedger
    return ReadOnlyLedger(database_url=database_url)


def _budget(now: datetime, database_url: str, daily_limit: int, rolling_limit: int) -> dict:
    today = now.astimezone(timezone.utc).date()
    start = today - timedelta(days=30)
    ledger = _read_only_ledger(database_url)
    with ledger.snapshot():
        with ledger.connect() as db:
            rows = db.execute(USAGE_QUERY, (start.isoformat(), today.isoformat())).fetchmany(32)
    if len(rows) > 31:
        raise ValueError('Invalid recorded usage')
    days = set()
    daily_used = rolling_used = 0
    for row in rows:
        if len(row) != 2:
            raise ValueError('Invalid recorded usage')
        raw_day, credits = row
        if not isinstance(raw_day, str):
            raise ValueError('Invalid recorded usage')
        day = date.fromisoformat(raw_day)
        if (day.isoformat() != raw_day or not start <= day <= today or day in days
                or type(credits) is not int or not 0 <= credits <= MAX_SAFE_INTEGER):
            raise ValueError('Invalid recorded usage')
        days.add(day)
        rolling_used += credits
        if day == today:
            daily_used = credits
    if rolling_used > MAX_SAFE_INTEGER:
        raise ValueError('Invalid recorded usage')
    return dict(status='observed', utc_day=today.isoformat(), rolling_start=start.isoformat(),
                rolling_end=today.isoformat(), recorded_days=len(days), daily_limit=daily_limit,
                daily_used=daily_used, daily_remaining=max(0, daily_limit-daily_used),
                rolling_limit=rolling_limit, rolling_used=rolling_used,
                rolling_remaining=max(0, rolling_limit-rolling_used))


def _header_integer(headers: httpx.Headers, name: str) -> int:
    value = headers.get(name)
    if not isinstance(value, str) or not re.fullmatch(r'0|[1-9][0-9]{0,15}', value):
        raise _ProviderUnavailable('invalid_headers')
    result = int(value)
    if result > MAX_SAFE_INTEGER:
        raise _ProviderUnavailable('invalid_headers')
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate response key')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError('Invalid JSON constant')


def _sports(body: bytes) -> dict:
    values = json.loads(body, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    if not isinstance(values, list) or not 1 <= len(values) <= 1024:
        raise ValueError('Invalid sports response')
    active = {}
    for value in values:
        if (not isinstance(value, dict) or not isinstance(value.get('key'), str)
                or not re.fullmatch(r'[a-z0-9_]{1,80}', value['key'])
                or value['key'] in active or type(value.get('active')) is not bool):
            raise ValueError('Invalid sports response')
        active[value['key']] = value['active']
    if any(key not in active for key in SPORT_KEYS.values()):
        raise ValueError('Required sport missing')
    return {sport: active[key] for sport, key in SPORT_KEYS.items()}


@contextmanager
def _private_request_logs():
    # This standalone diagnostic has no concurrent application work. Suppress URL
    # records, including dynamically created httpcore child loggers, then restore.
    previous = logging.root.manager.disable
    logging.disable(max(previous, logging.CRITICAL))
    try:
        yield
    finally:
        logging.disable(previous)


async def _provider(key: str) -> dict:
    transport = httpx.AsyncHTTPTransport(retries=0, verify=True, trust_env=False)
    with _private_request_logs():
        async with asyncio.timeout(15):
            async with httpx.AsyncClient(transport=transport, verify=True, trust_env=False,
                    follow_redirects=False, timeout=httpx.Timeout(5)) as client:
                async with client.stream('GET', SPORTS_URL,
                        params={'apiKey': key, 'all': 'true'},
                        headers={'Accept-Encoding': 'identity'}) as response:
                    if response.status_code != 200:
                        raise _ProviderUnavailable('http_status', response.status_code)
                    if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                        raise _ProviderUnavailable('invalid_body')
                    headers = {name: _header_integer(response.headers, 'x-requests-'+name)
                               for name in ('remaining', 'used', 'last')}
                    if headers['last'] != 0:
                        raise _ProviderUnavailable('nonzero_request_cost')
                    length = response.headers.get('content-length')
                    if length is not None and (not re.fullmatch(r'0|[1-9][0-9]{0,8}', length)
                                               or int(length) > MAX_RESPONSE_BYTES):
                        raise _ProviderUnavailable('response_too_large')
                    body = bytearray()
                    async for chunk in response.aiter_raw(chunk_size=16384):
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise _ProviderUnavailable('response_too_large')
                        body.extend(chunk)
                    try:
                        sports = _sports(bytes(body))
                    except (ValueError, TypeError, RecursionError):
                        raise _ProviderUnavailable('invalid_body') from None
    return dict(status='observed', sports_active=sports, usage=headers)


async def run_check(now: datetime, key: str | None, database_url: str | None,
                    daily_limit: int, *, rolling_limit: int = 450) -> dict:
    """Observe prerequisites only; exhausted allowances are valid observations."""
    report = _base_report(now)
    try:
        if isinstance(key, str) and key != key.strip():
            raise ValueError('Invalid configured credential')
        key = require_safe_odds_api_key(key)
    except Exception:
        missing = key is None or (isinstance(key, str) and not key.strip())
        report['credential'] = dict(status='unavailable',
            reason='credential_not_configured' if missing else 'credential_rejected')
        return report
    report['credential'] = dict(status='observed')
    try:
        if (not isinstance(now, datetime) or now.utcoffset() is None
                or type(daily_limit) is not int or not 1 <= daily_limit <= 20
                or type(rolling_limit) is not int or not 1 <= rolling_limit <= 450):
            raise ValueError('Invalid observation configuration')
        database_url = _hosted_url(database_url)
    except Exception:
        report['local_budget'] = dict(status='unavailable', reason='invalid_configuration')
        return report
    try:
        report['local_budget'] = _budget(now, database_url, daily_limit, rolling_limit)
    except Exception:
        report['local_budget'] = dict(status='unavailable', reason='ledger_unavailable')
        return report
    try:
        report['provider'] = await _provider(key)
    except _ProviderUnavailable as error:
        report['provider'] = dict(status='unavailable', reason=error.reason)
        if error.http_status is not None:
            report['provider']['http_status'] = error.http_status
        return report
    except (TimeoutError, httpx.TimeoutException):
        report['provider'] = dict(status='unavailable', reason='provider_timeout')
        return report
    except Exception:
        report['provider'] = dict(status='unavailable', reason='provider_unavailable')
        return report
    report['status'] = 'observed'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daily-credit-limit', default='20')
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    try:
        report = asyncio.run(run_check(now, os.environ.get('ODDS_API_KEY'),
            os.environ.get('ANALYTICS_DATABASE_URL'), int(args.daily_credit_limit),
            rolling_limit=int(os.environ.get('ODDS_ROLLING_CREDIT_LIMIT', '450'))))
    except Exception:
        report = _base_report(now)
        report['reason'] = 'invalid_configuration'
    print(json.dumps(report, separators=(',', ':'), allow_nan=False))
    if report['status'] != 'observed':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
