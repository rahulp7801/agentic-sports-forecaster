"""The legacy one-game CLI may not spend Odds API credits outside shared policy."""
import runpy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from sportsbet.config import settings


@pytest.fixture
def scanner():
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / "scan_game_ev.py"))


class FakeResponse:
    def __init__(self, payload, *, remaining="100"):
        self.payload = payload
        self.headers = {} if remaining is None else {"x-requests-remaining": remaining}

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def get(self, url, **kwargs):
        self.calls.append(url)
        return self.responses[len(self.calls) - 1]


class FakeLedger:
    def __init__(self, *, allow=True):
        self.allow = allow
        self.calls = []

    def reserve_api_credits_with_reason(self, cost, limit, holdback):
        self.calls.append((cost, limit, holdback))
        return self.allow, "reserved" if self.allow else "daily_credit_limit"


def event(event_id, home="New York Knicks", away="Houston Rockets", *, start=None):
    start = start or datetime.now(timezone.utc) + timedelta(days=1)
    return {"id": event_id, "home_team": home, "away_team": away,
            "commence_time": start.isoformat()}


def configure(monkeypatch, scanner, client, ledger):
    monkeypatch.setattr(settings, "odds_api_key", "test-only")
    monkeypatch.setattr(settings, "analytics_database_url", "postgresql://test-only")
    monkeypatch.setattr(settings, "odds_rolling_credit_limit", 450)
    fn = scanner["_fetch_odds_api_snapshots"]
    monkeypatch.setitem(fn.__globals__, "Ledger", lambda: ledger)
    monkeypatch.setattr(fn.__globals__["httpx"], "AsyncClient", lambda **_: client)
    return fn


@pytest.mark.asyncio
async def test_local_scanner_fails_closed_without_shared_ledger_or_approved_cap(
    monkeypatch, scanner,
):
    client, ledger = FakeClient([]), FakeLedger()
    fn = configure(monkeypatch, scanner, client, ledger)
    start = datetime.now(timezone.utc) + timedelta(days=1)
    day = start.astimezone(ZoneInfo("America/New_York")).date()
    monkeypatch.setattr(settings, "analytics_database_url", None)
    assert await fn(home_team="NY", away_team="HOU", target_date=day) == []
    monkeypatch.setattr(settings, "analytics_database_url", "postgresql://test-only")
    monkeypatch.setattr(settings, "odds_rolling_credit_limit", 451)
    assert await fn(home_team="NY", away_team="HOU", target_date=day) == []
    assert client.calls == ledger.calls == []


@pytest.mark.asyncio
async def test_local_scanner_requires_reservation_and_provider_remaining(
    monkeypatch, scanner,
):
    start = datetime.now(timezone.utc) + timedelta(days=1)
    day = start.astimezone(ZoneInfo("America/New_York")).date()
    client, ledger = FakeClient([FakeResponse([event("one", start=start)])]), FakeLedger(allow=False)
    fn = configure(monkeypatch, scanner, client, ledger)
    assert await fn(home_team="NY", away_team="HOU", target_date=day) == []
    assert len(client.calls) == 1  # Free discovery only; paid detail is blocked.
    assert ledger.calls == [(6, 20, 12)]

    client, ledger = FakeClient([FakeResponse([event("one", start=start)], remaining=None)]), FakeLedger()
    fn = configure(monkeypatch, scanner, client, ledger)
    assert await fn(home_team="NY", away_team="HOU", target_date=day) == []
    assert len(client.calls) == 1
    assert ledger.calls == []


@pytest.mark.asyncio
async def test_local_scanner_quotes_only_exact_unlocked_game(monkeypatch, scanner):
    start = datetime.now(timezone.utc) + timedelta(days=1)
    day = start.astimezone(ZoneInfo("America/New_York")).date()
    exact = event("target", start=start)
    unrelated = event("other", "Los Angeles Lakers", "Boston Celtics", start=start)
    client = FakeClient([
        FakeResponse([unrelated, exact]),
        FakeResponse(exact | {"bookmakers": []}),
    ])
    ledger = FakeLedger()
    fn = configure(monkeypatch, scanner, client, ledger)
    assert await fn(home_team="NY", away_team="HOU", target_date=day) == []
    assert len(client.calls) == 2
    assert client.calls[1].endswith("/events/target/odds")
    assert ledger.calls == [(6, 20, 12)]


@pytest.mark.asyncio
async def test_local_scanner_skips_ambiguous_or_locked_game(monkeypatch, scanner):
    start = datetime.now(timezone.utc) + timedelta(days=1)
    day = start.astimezone(ZoneInfo("America/New_York")).date()
    locked_start = datetime.now(timezone.utc) + timedelta(minutes=20)
    for events, target_day in (
        ([event("a", start=start), event("b", start=start)], day),
        ([event("locked", start=locked_start)],
         locked_start.astimezone(ZoneInfo("America/New_York")).date()),
    ):
        client, ledger = FakeClient([FakeResponse(events)]), FakeLedger()
        fn = configure(monkeypatch, scanner, client, ledger)
        assert await fn(home_team="NY", away_team="HOU", target_date=target_day) == []
        assert len(client.calls) == 1
        assert ledger.calls == []


@pytest.mark.asyncio
async def test_local_scanner_rejects_cross_game_quote_response(monkeypatch, scanner):
    start = datetime.now(timezone.utc) + timedelta(days=1)
    day = start.astimezone(ZoneInfo("America/New_York")).date()
    exact = event("target", start=start)
    other = event("other", "Los Angeles Lakers", "Boston Celtics", start=start)
    client = FakeClient([FakeResponse([exact]), FakeResponse(other | {"bookmakers": [{}]})])
    ledger = FakeLedger()
    fn = configure(monkeypatch, scanner, client, ledger)
    assert await fn(home_team="NY", away_team="HOU", target_date=day) == []
    assert len(client.calls) == 2
    assert ledger.calls == [(6, 20, 12)]
