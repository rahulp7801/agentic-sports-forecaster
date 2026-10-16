from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import sys

import httpx
import pytest

from sportsbet import provider_readiness as readiness
from sportsbet.ingestion import odds_api_credential


NOW = datetime(2026, 10, 16, 23, 30, tzinfo=timezone.utc)
KEY = 'mock-only-provider-key'
DSN = 'postgresql://worker:mock-only-password@db.example.test/analytics?sslmode=verify-full'
HEADERS = {'x-requests-remaining': '500', 'x-requests-used': '0', 'x-requests-last': '0'}
SPORTS = [dict(key=key, active=sport != 'nba') for sport, key in readiness.SPORT_KEYS.items()]
SENSITIVE = (KEY, 'mock-only-password', DSN, 'RAW_PROVIDER_SECRET', readiness.SPORTS_URL)


@pytest.fixture
def probes(monkeypatch):
    state = dict(rows=[('2026-09-16', 7), ('2026-10-15', 3), ('2026-10-16', 2)],
                 database_error=None, provider_error=None, status=200, headers=dict(HEADERS),
                 body=json.dumps(SPORTS).encode(), chunks=None, requests=[], database=[],
                 snapshots=0, connections=0, response_closed=False, client_closed=False)

    class Cursor:
        def fetchmany(self, size):
            assert size == 32
            return state['rows'][:size]

    class Database:
        def execute(self, sql, args):
            assert sql == readiness.USAGE_QUERY
            assert sql.startswith('SELECT ') and args == ('2026-09-16', '2026-10-16')
            state['database'].append((sql, args))
            if state['database_error']:
                raise state['database_error']
            return Cursor()

    class Ledger:
        @contextmanager
        def snapshot(self):
            state['snapshots'] += 1
            yield self

        @contextmanager
        def connect(self):
            state['connections'] += 1
            yield Database()

    def ledger(database_url):
        assert database_url == DSN
        return Ledger()

    class Response:
        @property
        def status_code(self):
            return state['status']

        @property
        def headers(self):
            return httpx.Headers(state['headers'])

        async def __aenter__(self):
            logging.getLogger('httpx').info('Authenticated URL %s?apiKey=%s', readiness.SPORTS_URL, KEY)
            logging.getLogger('httpcore.connection.new_trace').debug('RAW_PROVIDER_SECRET %s', DSN)
            if state['provider_error']:
                raise state['provider_error']
            return self

        async def __aexit__(self, *args):
            state['response_closed'] = True

        async def aiter_raw(self, *, chunk_size):
            assert chunk_size == 16384
            for chunk in state['chunks'] if state['chunks'] is not None else [state['body']]:
                yield chunk

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            state['client_closed'] = True

        def stream(self, method, url, *, params, headers):
            state['requests'].append((method, url))
            assert method == 'GET' and url == readiness.SPORTS_URL
            assert params == {'apiKey': KEY, 'all': 'true'}
            assert headers == {'Accept-Encoding': 'identity'}
            return Response()

    transport = object()

    def create_transport(**kwargs):
        assert kwargs == dict(retries=0, verify=True, trust_env=False)
        return transport

    def create_client(**kwargs):
        assert kwargs['transport'] is transport and kwargs['verify'] is True
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        timeout = kwargs['timeout']
        assert all(getattr(timeout, name) == 5 for name in ('connect', 'read', 'write', 'pool'))
        return Client()

    monkeypatch.setattr(readiness, '_read_only_ledger', ledger)
    monkeypatch.setattr(readiness.httpx, 'AsyncHTTPTransport', create_transport)
    monkeypatch.setattr(readiness.httpx, 'AsyncClient', create_client)
    return state


def assert_private(report):
    text = json.dumps(report)
    assert all(value not in text for value in SENSITIVE)
    assert report['activation_authorized'] is False
    assert report['free_plan_verified'] is False
    assert report['reserve_not_evaluated'] is True


@pytest.mark.asyncio
async def test_one_free_sports_request_and_consistent_read_only_budget(probes, caplog):
    caplog.set_level(logging.DEBUG)
    previous = logging.root.manager.disable
    report = await readiness.run_check(NOW, KEY, DSN, 20)
    assert report['status'] == 'observed'
    assert report['captured_at'] == NOW.isoformat()
    assert report['provider'] == dict(status='observed', sports_active=dict(nfl=True, nba=False, cfb=True),
                                      usage=dict(remaining=500, used=0, last=0))
    assert report['local_budget'] == dict(status='observed', utc_day='2026-10-16', rolling_start='2026-09-16',
        rolling_end='2026-10-16', recorded_days=3, daily_limit=20, daily_used=2, daily_remaining=18,
        rolling_limit=450, rolling_used=12, rolling_remaining=438)
    assert probes['requests'] == [('GET', readiness.SPORTS_URL)]
    assert len(probes['database']) == probes['snapshots'] == probes['connections'] == 1
    assert probes['response_closed'] and probes['client_closed']
    assert caplog.text == '' and logging.root.manager.disable == previous
    assert_private(report)


@pytest.mark.asyncio
@pytest.mark.parametrize('key', [None, '', '   ', 'mock-historically-exposed-key',
    ' mock-historically-exposed-key', 'mock-historically-exposed-key\n', ' '+KEY])
async def test_missing_exposed_or_padded_key_prevents_database_and_http(probes, monkeypatch, key):
    monkeypatch.setattr(odds_api_credential, '_EXPOSED_KEY_SHA256',
                        hashlib.sha256(b'mock-historically-exposed-key').hexdigest())
    report = await readiness.run_check(NOW, key, DSN, 20)
    assert report['status'] == 'unavailable' and report['credential']['status'] == 'unavailable'
    assert report['credential']['reason'] in ('credential_not_configured', 'credential_rejected')
    assert not probes['database'] and not probes['requests'] and probes['snapshots'] == 0
    assert_private(report)


@pytest.mark.asyncio
@pytest.mark.parametrize('database_url', [None, '', 'sqlite:///local', 'postgresql:///local',
    'postgresql://localhost/local', 'postgresql://127.0.0.1/local', 'postgresql://[::1]/local'])
async def test_requires_explicit_hosted_analytics_source_without_fallback(probes, monkeypatch, database_url):
    monkeypatch.setenv('DATABASE_URL', DSN)
    report = await readiness.run_check(NOW, KEY, database_url, 20)
    assert report['status'] == 'unavailable'
    assert report['local_budget'] == dict(status='unavailable', reason='invalid_configuration')
    assert probes['snapshots'] == 0 and not probes['requests']
    assert_private(report)


@pytest.mark.asyncio
@pytest.mark.parametrize('daily,rolling,clock', [(21, 450, NOW), (0, 450, NOW), (True, 450, NOW),
    (20, 451, NOW), (20, 0, NOW), (20, True, NOW), (20, 450, NOW.replace(tzinfo=None))])
async def test_limits_and_aware_clock_cannot_bypass_approved_caps(probes, daily, rolling, clock):
    report = await readiness.run_check(clock, KEY, DSN, daily, rolling_limit=rolling)
    assert report['status'] == 'unavailable' and not probes['database'] and not probes['requests']
    assert report['local_budget']['reason'] == 'invalid_configuration'
    assert_private(report)


@pytest.mark.asyncio
@pytest.mark.parametrize('rows', [[('2026-10-16', -1)], [('2026-10-16', True)],
    [('2026-10-16', '1')], [('2026-10-16', 1.0)], [('2026-10-16', 2**53)],
    [('2026-09-15', 1)], [('2026-10-17', 1)], [('20261016', 1)], [('not-a-date', 1)],
    [(NOW.date(), 1)], [('2026-10-16', 1), ('2026-10-16', 2)], [('2026-10-16', 1, 2)],
    [('2026-10-16', 1)] * 32])
async def test_invalid_recorded_usage_stops_before_provider(probes, rows):
    probes['rows'] = rows
    report = await readiness.run_check(NOW, KEY, DSN, 20)
    assert report['local_budget'] == dict(status='unavailable', reason='ledger_unavailable')
    assert not probes['requests']
    assert_private(report)


@pytest.mark.asyncio
async def test_database_failure_is_redacted_and_does_not_probe_provider(probes):
    probes['database_error'] = RuntimeError('RAW_PROVIDER_SECRET '+DSN)
    report = await readiness.run_check(NOW, KEY, DSN, 20)
    assert report['local_budget'] == dict(status='unavailable', reason='ledger_unavailable')
    assert not probes['requests']
    assert_private(report)


@pytest.mark.asyncio
@pytest.mark.parametrize('rows', [[], [('2026-10-16', 20), ('2026-10-15', 450)]])
async def test_empty_and_exhausted_usage_are_observations_not_collection_authorization(probes, rows):
    probes['rows'] = rows
    probes['headers'] = dict(HEADERS, **{'x-requests-remaining': '0', 'x-requests-used': '500'})
    report = await readiness.run_check(NOW, KEY, DSN, 20)
    assert report['status'] == 'observed' and report['provider']['usage']['remaining'] == 0
    if rows:
        assert report['local_budget']['daily_remaining'] == report['local_budget']['rolling_remaining'] == 0
    else:
        assert report['local_budget']['daily_used'] == report['local_budget']['rolling_used'] == 0
    assert_private(report)


@pytest.mark.asyncio
@pytest.mark.parametrize('header,value', [('remaining', None), ('used', '-1'), ('last', '1'),
    ('last', '0.0'), ('remaining', ' 1'), ('remaining', '+1'), ('remaining', '01'),
    ('remaining', str(2**53)), ('used', 'RAW_PROVIDER_SECRET')])
async def test_unavailable_allowance_headers_are_never_inferred_or_echoed(probes, header, value):
    name = 'x-requests-'+header
    if value is None:
        del probes['headers'][name]
    else:
        probes['headers'][name] = value
    report = await readiness.run_check(NOW, KEY, DSN, 20)
    reason = 'nonzero_request_cost' if (header, value) == ('last', '1') else 'invalid_headers'
    assert report['status'] == 'unavailable'
    assert report['provider'] == dict(status='unavailable', reason=reason)
    assert len(probes['requests']) == 1 and probes['client_closed']
    assert_private(report)


@pytest.mark.asyncio
@pytest.mark.parametrize('sports', [None, {}, [], [dict(key='basketball_nba', active=False)],
    SPORTS+[SPORTS[0]], [dict(key=row['key'], active=1) for row in SPORTS],
    [dict(key='RAW_PROVIDER_SECRET', active=True)]+SPORTS,
    [dict(key=row['key']) for row in SPORTS]])
async def test_malformed_missing_or_duplicate_sports_are_unavailable(probes, sports):
    probes['body'] = json.dumps(sports).encode()
    report = await readiness.run_check(NOW, KEY, DSN, 20)
    assert report['status'] == 'unavailable'
    assert report['provider'] == dict(status='unavailable', reason='invalid_body')
    assert_private(report)


@pytest.mark.asyncio
@pytest.mark.parametrize('body', [b'RAW_PROVIDER_SECRET', b'[{"key":"basketball_nba","active":true,"active":false}]',
                                  b'[NaN]', b'\xff'])
async def test_invalid_json_has_no_raw_response_diagnostics(probes, body):
    probes['body'] = body
    report = await readiness.run_check(NOW, KEY, DSN, 20)
    assert report['provider'] == dict(status='unavailable', reason='invalid_body')
    assert_private(report)


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [301, 302, 307, 401, 429, 500])
async def test_redirects_and_http_failures_do_not_retry_or_expose_body(probes, status):
    probes['status'] = status
    probes['headers']['location'] = 'https://other.example.test/?key='+KEY
    probes['body'] = b'RAW_PROVIDER_SECRET'
    report = await readiness.run_check(NOW, KEY, DSN, 20)
    assert report['provider'] == dict(status='unavailable', reason='http_status', http_status=status)
    assert len(probes['requests']) == 1 and probes['response_closed'] and probes['client_closed']
    assert_private(report)


@pytest.mark.asyncio
@pytest.mark.parametrize('error,reason', [(TimeoutError('RAW_PROVIDER_SECRET'), 'provider_timeout'),
    (httpx.ReadTimeout('RAW_PROVIDER_SECRET '+KEY), 'provider_timeout'),
    (httpx.ConnectError('RAW_PROVIDER_SECRET '+DSN), 'provider_unavailable')])
async def test_provider_failures_are_redacted_and_logging_state_restored(probes, caplog, error, reason):
    probes['provider_error'] = error
    caplog.set_level(logging.DEBUG)
    previous = logging.root.manager.disable
    report = await readiness.run_check(NOW, KEY, DSN, 20)
    assert report['provider'] == dict(status='unavailable', reason=reason)
    assert len(probes['requests']) == 1 and probes['client_closed']
    assert caplog.text == '' and logging.root.manager.disable == previous
    assert_private(report)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['length', 'stream', 'encoding'])
async def test_bounded_response_rejects_declared_streamed_and_compressed_overflow(probes, mode):
    if mode == 'length':
        probes['headers']['content-length'] = str(readiness.MAX_RESPONSE_BYTES+1)
    elif mode == 'stream':
        probes['chunks'] = [b'x'*16384]*17
    else:
        probes['headers']['content-encoding'] = 'gzip'
    report = await readiness.run_check(NOW, KEY, DSN, 20)
    reason = 'invalid_body' if mode == 'encoding' else 'response_too_large'
    assert report['provider'] == dict(status='unavailable', reason=reason)
    assert len(probes['requests']) == 1 and probes['response_closed'] and probes['client_closed']
    assert_private(report)


@pytest.mark.parametrize('status', ['observed', 'unavailable'])
def test_cli_only_prints_sanitized_observation_and_preserves_explicit_source(monkeypatch, capsys, status):
    async def check(now, key, database_url, daily_limit, *, rolling_limit):
        assert now.utcoffset() == timedelta(0)
        assert key == KEY and database_url is None and daily_limit == 12 and rolling_limit == 400
        report = readiness._base_report(NOW)
        report['status'] = status
        return report
    monkeypatch.setattr(readiness, 'run_check', check)
    monkeypatch.setattr(sys, 'argv', ['provider_readiness', '--daily-credit-limit', '12'])
    monkeypatch.setenv('ODDS_API_KEY', KEY)
    monkeypatch.setenv('DATABASE_URL', DSN)
    monkeypatch.delenv('ANALYTICS_DATABASE_URL', raising=False)
    monkeypatch.setenv('ODDS_ROLLING_CREDIT_LIMIT', '400')
    if status == 'unavailable':
        with pytest.raises(SystemExit) as error:
            readiness.main()
        assert error.value.code == 2
    else:
        readiness.main()
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report['status'] == status and captured.err == ''
    assert_private(report)


@pytest.mark.parametrize('invalid', ['daily', 'rolling'])
def test_cli_configuration_error_is_redacted(monkeypatch, capsys, invalid):
    args = ['--daily-credit-limit', 'RAW_PROVIDER_SECRET'] if invalid == 'daily' else []
    monkeypatch.setattr(sys, 'argv', ['provider_readiness']+args)
    monkeypatch.setenv('ODDS_ROLLING_CREDIT_LIMIT', 'RAW_PROVIDER_SECRET' if invalid == 'rolling' else '450')
    with pytest.raises(SystemExit) as error:
        readiness.main()
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.err == ''
    report = json.loads(captured.out)
    assert report['status'] == 'unavailable'
    assert_private(report)
