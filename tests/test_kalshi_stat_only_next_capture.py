"""A missed or repeated one-shot window makes zero public requests."""
import asyncio
from datetime import datetime, timedelta, timezone
import json

import pytest

from sportsbet.quant import kalshi_stat_only_next_capture as runner


def test_late_attempt_does_not_start_network_or_create_receipt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    private = tmp_path/'.local'
    private.mkdir()
    schedule = private/'games.parquet'
    schedule.write_bytes(b'pinned schedule')
    current = datetime(2026, 10, 7, 14, tzinfo=timezone.utc)
    called = []
    monkeypatch.setattr(runner, 'stage', lambda *args, **kwargs: called.append('stage'))
    monkeypatch.setattr(runner, 'watch', lambda *args, **kwargs: called.append('watch'))
    with pytest.raises(ValueError, match='window'):
        asyncio.run(runner.capture(private/'week5', schedule,
            window_start=current-timedelta(hours=2),
            window_end=current-timedelta(hours=1), now=lambda: current))
    assert called == []
    assert not (private/'week5').exists()


def test_existing_attempt_does_not_repeat_network(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    private = tmp_path/'.local'
    private.mkdir()
    output = private/'week5'
    output.mkdir()
    schedule = private/'games.parquet'
    schedule.write_bytes(b'pinned schedule')
    current = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
    called = []
    monkeypatch.setattr(runner, 'stage', lambda *args, **kwargs: called.append('stage'))
    with pytest.raises(ValueError, match='One-shot'):
        asyncio.run(runner.capture(output, schedule,
            window_start=current-timedelta(hours=1),
            window_end=current+timedelta(hours=1), now=lambda: current))
    assert called == []


def test_one_attempt_keeps_private_hash_committed_receipts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    private = tmp_path/'.local'
    private.mkdir()
    schedule = private/'games.parquet'
    schedule.write_bytes(b'pinned schedule')
    archive = private/'archive.json'
    archive.write_text('{"evidence": {}}', encoding='utf-8')
    current = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
    events = []

    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    class Reader:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    def stage(path, **kwargs):
        events.append('source')
        path.mkdir()
        (path/'source-manifest.json').write_text('{}', encoding='utf-8')
        # A shared schedule refresh during collection must not change this
        # attempt's already captured inputs.
        schedule.write_bytes(b'new shared schedule')
        return {}

    async def watch(*args, **kwargs):
        assert kwargs['provider'] == 'kalshi'
        assert args[3] is False
        assert runner.market_watch.KalshiReader is Reader
        events.append('market')
        return {'sources': {'kalshi': {'status': 'observed'}}}, archive

    def pair(*args, **kwargs):
        events.append('pair')
        return {'selected_contracts': 4, 'forecast_contracts': 3}

    async def quotes(*args, **kwargs):
        events.append('quotes')
        return {'evidence': {'pages': []}}

    monkeypatch.setattr(runner.httpx, 'Client', Client)
    monkeypatch.setattr(runner, 'stage', stage)
    monkeypatch.setattr(runner, 'capture_context', lambda *args, **kwargs: (
        events.append('context') or {'status': 'unavailable'}))
    def verify_source_week(source_dir, captured_schedule, **kwargs):
        events.append('source_week')
        assert captured_schedule.read_bytes() == b'pinned schedule'
        assert captured_schedule == private/'week5/schedule.parquet'
        return {'week': 4}

    monkeypatch.setattr(runner, 'verify_source_week', verify_source_week)
    monkeypatch.setattr(runner, 'verify_receiving_source', lambda *args, **kwargs: (
        events.append('receiving_source') or {'protocol': 'reconciled'}))
    monkeypatch.setattr(runner, 'watch', watch)
    monkeypatch.setattr(runner, 'pair_capture', pair)
    monkeypatch.setattr(runner, 'transfer', lambda *args, **kwargs: {
        'predicted_contracts': 2})
    monkeypatch.setattr(runner, 'UnsignedReader', Reader)
    monkeypatch.setattr(runner, 'quote_capture', quotes)
    monkeypatch.setattr(runner, 'paper_freeze', lambda *args, **kwargs: {
        'candidates_count': 1, 'candidate_games': 1})
    monkeypatch.setattr(runner, 'prior20_control', lambda *args, **kwargs: {
        'protocol': 'strict-prior20'})
    monkeypatch.setattr(runner, 'commit', lambda *args, **kwargs: {
        'protocol': 'pregame-commitment'})
    monkeypatch.setattr(runner, 'freeze_recent_gap', lambda *args: {'protocol': 'frozen-recent-gap'})
    monkeypatch.setattr(runner, 'freeze_role_weighting', lambda *args, **kwargs: (
        events.append('role_weighting') or {'protocol': 'frozen-role-weighting'}))

    report = asyncio.run(runner.capture(private/'week5', schedule,
        window_start=current-timedelta(minutes=1),
        window_end=current+timedelta(minutes=1), now=lambda: current))
    assert events == ['source', 'context', 'source_week', 'receiving_source', 'market', 'pair', 'role_weighting', 'quotes']
    assert report['complete_source_week'] == 4
    assert report['paper_candidates'] == 1
    assert not report['edge_established']
    assert json.loads((private/'week5/commitment.json').read_text()) == {
        'protocol': 'pregame-commitment'}
    assert (private/'week5/schedule.parquet').read_bytes() == b'pinned schedule'
    assert schedule.read_bytes() == b'new shared schedule'
    assert json.loads((private/'week5/recent-gap.json').read_text()) == {'protocol': 'frozen-recent-gap'}
    assert json.loads((private/'week5/source-receiving.json').read_text()) == {'protocol': 'reconciled'}
    assert json.loads((private/'week5/role-weighting.json').read_text()) == {'protocol': 'frozen-role-weighting'}


@pytest.mark.parametrize('failure', ['source_week', 'receiving_source'])
def test_incomplete_recent_week_stops_before_public_market_read(tmp_path, monkeypatch, failure):
    monkeypatch.chdir(tmp_path)
    private = tmp_path/'.local'
    private.mkdir()
    schedule = private/'games.parquet'
    schedule.write_bytes(b'pinned schedule')
    current = datetime(2026, 10, 8, 17, tzinfo=timezone.utc)
    events = []

    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def stage(path, **kwargs):
        events.append('source')
        path.mkdir()
        return {}

    def stale(*args, **kwargs):
        events.append(failure)
        raise ValueError('Latest complete NFL week source integrity failed')

    monkeypatch.setattr(runner.httpx, 'Client', Client)
    monkeypatch.setattr(runner, 'stage', stage)
    monkeypatch.setattr(runner, 'capture_context', lambda *args, **kwargs: (
        events.append('context') or {'status': 'unavailable'}))
    monkeypatch.setattr(runner, 'verify_source_week', stale)
    if failure == 'receiving_source':
        monkeypatch.setattr(runner, 'verify_source_week', lambda *args, **kwargs: (
            events.append('source_week') or {'week': 4}))
        monkeypatch.setattr(runner, 'verify_receiving_source', stale)
    monkeypatch.setattr(runner, 'watch', lambda *args, **kwargs: events.append('market'))
    with pytest.raises(ValueError, match='Latest complete NFL week'):
        asyncio.run(runner.capture(private/'week5', schedule,
            window_start=current-timedelta(minutes=1),
            window_end=current+timedelta(minutes=1), now=lambda: current))
    assert events == ['source', 'context', 'source_week'] + (['receiving_source'] if failure == 'receiving_source' else [])
    assert (private/'week5/attempt.json').is_file()
    assert (private/'week5/source-week.json').exists() is (failure == 'receiving_source')
    assert not (private/'week5/source-receiving.json').exists()
