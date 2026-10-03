"""Future venue result capture cannot read before the full committed gate."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from sportsbet.quant import kalshi_stat_only_next_settlement_capture as collector
from sportsbet.quant.clock_attestation import HOSTS, VERSION as CLOCK_VERSION
from sportsbet.quant.kalshi_market_cohort import digest


def test_future_result_collector_refuses_early_venue_read(monkeypatch):
    now = datetime(2026, 10, 12, tzinfo=timezone.utc)
    called = []

    class Reader:
        async def settled_markets(self, *args, **kwargs):
            called.append('venue')

    monkeypatch.setattr(collector.next_eval, 'committed_preflight',
        lambda *args: ({}, {'first_eligible_settlement_at':
            (now+timedelta(hours=1)).isoformat()}, {}))
    with pytest.raises(ValueError, match='premature'):
        asyncio.run(collector.capture({}, None, {}, Reader(), {}, now=now))
    assert called == []


def test_future_result_collector_requires_commitment_before_venue_read(monkeypatch):
    now = datetime(2026, 10, 13, tzinfo=timezone.utc)
    called = []

    class Reader:
        async def settled_markets(self, *args, **kwargs):
            called.append('venue')

    def reject(*args):
        raise ValueError('Pregame input hash changed')

    monkeypatch.setattr(collector.next_eval, 'committed_preflight', reject)
    with pytest.raises(ValueError, match='hash changed'):
        asyncio.run(collector.capture({}, None, {}, Reader(), {}, now=now))
    assert called == []


def test_full_gate_keeps_raw_exact_contract_receipt(monkeypatch):
    now = datetime(2026, 10, 13, 6, 20, tzinfo=timezone.utc)
    gate = datetime(2026, 10, 13, 6, 15, tzinfo=timezone.utc)
    called = []
    proof = {'protocol': CLOCK_VERSION, 'checked_at': now.isoformat(),
             'local_clock_acceptable': True,
             'observations': [dict(host=host,
                 request_started_at=(now-timedelta(seconds=2)).isoformat(),
                 response_received_at=(now-timedelta(seconds=1)).isoformat(),
                 server_date=(now-timedelta(seconds=1)).isoformat(),
                 rtt_seconds=1, server_minus_local_seconds=.5,
                 age=None, http_status=200) for host in HOSTS]}

    class Reader:
        async def settled_markets(self, *args, **kwargs):
            called.append('venue')

    monkeypatch.setattr(collector.next_eval, 'committed_preflight',
        lambda *args: ({'pair': {}, 'market': {}},
            {'first_eligible_settlement_at': gate.isoformat(),
             'original_market_contracts': 3}, {}))
    monkeypatch.setattr(collector, 'unpack', lambda pair: ({'selections': []}, {}))
    monkeypatch.setattr(collector.venue, 'verify_cohort',
                        lambda market, cohort: [None]*3)

    async def collect(*args, **kwargs):
        called.append('collect')
        return {'evidence': {'pages': []}, 'evidence_sha256': 'source-hash'}

    monkeypatch.setattr(collector.venue, 'collect', collect)
    monkeypatch.setattr(collector.venue, 'audit',
                        lambda *args, **kwargs: {'complete': False})
    commitment = {'protocol': 'pregame'}
    receipt, report = asyncio.run(collector.capture(
        {}, None, commitment, Reader(), proof, now=now))
    assert called == ['collect']
    assert receipt['original_market_contracts'] == 3
    assert receipt['pregame_commitment_sha256'] == digest(commitment)
    assert report['capture_record_sha256'] == receipt['record_sha256']
