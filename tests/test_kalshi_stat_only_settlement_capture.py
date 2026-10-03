from copy import deepcopy
from datetime import datetime, timezone
import httpx
import pytest

from sportsbet.quant import kalshi_stat_only_settlement_capture as capture
from sportsbet.quant.clock_attestation import HOSTS, VERSION as CLOCK_VERSION
from sportsbet.quant.kalshi_market_cohort import digest

GATE='2026-10-06T06:15:00+00:00'


def good_clock_proof():
    return {'protocol': CLOCK_VERSION, 'checked_at': '2026-10-06T06:20:00+00:00',
            'local_clock_acceptable': True,
            'observations': [dict(host=host, request_started_at=start,
                                  response_received_at=end, server_date=end,
                                  rtt_seconds=1, server_minus_local_seconds=.5,
                                  age=None, http_status=200)
                             for host, start, end in zip(HOSTS,
                                 ('2026-10-06T06:19:58+00:00',
                                  '2026-10-06T06:19:59+00:00'),
                                 ('2026-10-06T06:19:59+00:00',
                                  '2026-10-06T06:20:00+00:00'), strict=True)]}


def fixture(monkeypatch):
    monkeypatch.setattr(capture.frozen,'preflight',lambda *args: (
        {'first_eligible_settlement_at':GATE,'original_market_contracts':452},{}))
    monkeypatch.setattr(capture,'unpack',lambda pair: ({'selections':[]},{}))
    monkeypatch.setattr(capture.venue,'verify_cohort',lambda market,cohort: [None]*452)
    calls=[]
    async def collect(*args,**kwargs):
        calls.append('read')
        return dict(evidence={'pages':[]},evidence_sha256='source-hash')
    monkeypatch.setattr(capture.venue,'collect',collect)
    return calls


@pytest.mark.asyncio
async def test_result_capture_refuses_early_read_and_uses_full_denominator(monkeypatch):
    calls=fixture(monkeypatch)
    monkeypatch.setattr(capture.venue,'audit',lambda *args,**kwargs: dict(
        protocol=capture.venue.VERSION,selected_contracts=452,complete=False))
    proof=good_clock_proof()
    with pytest.raises(ValueError,match='premature'):
        await capture.capture({}, {}, {}, {}, {}, None, None, object(), proof,
                              now=datetime(2026,10,6,6,14,tzinfo=timezone.utc))
    assert calls==[]
    receipt, report=await capture.capture({}, {}, {}, {}, {}, None, None, object(),proof,
                              now=datetime(2026,10,6,6,20,tzinfo=timezone.utc))
    assert calls==['read']
    assert receipt['original_market_contracts']==452
    assert receipt['record_sha256']==digest({k:v for k,v in receipt.items() if k!='record_sha256'})
    assert report['capture_record_sha256']==receipt['record_sha256']
    assert report['complete'] is False


@pytest.mark.parametrize('field,value', [
    ('rtt_seconds', True), ('server_minus_local_seconds', False),
    ('age', False), ('age', '00'), ('http_status', 503),
    ('server_date', '2026-10-06T06:20:04+00:00'),
])
@pytest.mark.asyncio
async def test_invalid_clock_proof_refuses_before_venue_read(monkeypatch, field, value):
    calls = fixture(monkeypatch)
    proof = deepcopy(good_clock_proof())
    proof['observations'][0][field] = value
    with pytest.raises(ValueError, match='clock'):
        await capture.capture({}, {}, {}, {}, {}, None, None, object(), proof,
                              now=datetime(2026,10,6,6,20,tzinfo=timezone.utc))
    assert calls == []


@pytest.mark.parametrize('failure',[ValueError,AttributeError,RuntimeError])
@pytest.mark.asyncio
async def test_aggregate_failure_retains_raw_receipt_and_unsigned_boundary(monkeypatch,failure):
    fixture(monkeypatch)
    def fail(*args,**kwargs):raise failure('bad venue payload')
    monkeypatch.setattr(capture.venue,'audit',fail)
    proof=good_clock_proof()
    receipt, report=await capture.capture({}, {}, {}, {}, {}, None, None, object(),proof,
                              now=datetime(2026,10,6,6,20,tzinfo=timezone.utc))
    assert receipt['evidence_sha256']=='source-hash'
    assert report['evaluation']=='unavailable' and report['selected_contracts']==452
    with pytest.raises(RuntimeError,match='forbidden'):
        capture.UnsignedReader._headers(None,'/trade-api/v2/markets')

@pytest.mark.asyncio
async def test_nonobject_aggregate_report_retains_raw_receipt(monkeypatch):
    fixture(monkeypatch)
    monkeypatch.setattr(capture.venue,'audit',lambda *args,**kwargs: None)
    proof=good_clock_proof()
    receipt, report=await capture.capture({}, {}, {}, {}, {}, None, None, object(),proof,
                                  now=datetime(2026,10,6,6,20,tzinfo=timezone.utc))
    assert report['evaluation']=='unavailable' and report['error_type']=='TypeError'
    assert report['capture_record_sha256']==receipt['record_sha256']


@pytest.mark.asyncio
async def test_unsigned_exact_ticker_read_has_no_status_or_auth_filter():
    paths=[]
    def handler(request):
        paths.append((request.url.path,dict(request.url.params),dict(request.headers)))
        return httpx.Response(200,json={'markets':[],'cursor':''})
    async with capture.UnsignedReader(transport=httpx.MockTransport(handler)) as reader:
        assert await reader.settled_markets(['KXTEST-26-A'],historical=False)=={'markets':[],'cursor':''}
        with pytest.raises(ValueError,match='forbidden'):
            await reader.settled_markets(['KXTEST-26-A'],historical=True)
    assert len(paths)==1 and paths[0][0]=='/trade-api/v2/markets'
    assert paths[0][1]=={'tickers':'KXTEST-26-A','limit':'20'}
    assert not any(key.startswith('kalshi-access-') for key in paths[0][2])
