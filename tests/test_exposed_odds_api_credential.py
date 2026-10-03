"""The known public-history credential cannot reach paid-provider I/O."""

import hashlib

import pytest

from sportsbet.config import settings
from sportsbet.ingestion import odds_api_credential
from sportsbet.ingestion.odds_poller import OddsAPIPoller
from sportsbet import market_watch, scan


@pytest.fixture
def exposed_fixture(monkeypatch):
    # A disposable key tests the comparison without copying the real exposure.
    disposable = "disposable-test-credential"
    monkeypatch.setattr(
        odds_api_credential, "_EXPOSED_KEY_SHA256",
        hashlib.sha256(disposable.encode()).hexdigest(),
    )
    monkeypatch.setattr(settings, "odds_api_key", disposable)
    monkeypatch.setattr(settings, "analytics_database_url", "configured")
    return disposable


def test_exposed_key_rejected_without_echo_and_new_key_allowed(exposed_fixture):
    with pytest.raises(ValueError, match="revoked and rotated") as exc:
        odds_api_credential.require_safe_odds_api_key(exposed_fixture)
    assert exposed_fixture not in str(exc.value)
    assert odds_api_credential.require_safe_odds_api_key("new-disposable-key") == "new-disposable-key"


def test_legacy_poller_rejects_exposed_key_before_client_or_ledger(exposed_fixture):
    with pytest.raises(ValueError, match="revoked and rotated"):
        OddsAPIPoller(exposed_fixture, 1)


@pytest.mark.asyncio
async def test_paid_scan_rejects_exposed_key_before_ledger_or_network(monkeypatch, exposed_fixture):
    monkeypatch.setattr(scan, "Ledger", lambda: pytest.fail("ledger must not be opened"))
    with pytest.raises(ValueError, match="revoked and rotated"):
        await scan.run(["nfl"], 1)


@pytest.mark.asyncio
async def test_market_watch_rejects_exposed_key_before_ledger_or_network(monkeypatch, exposed_fixture):
    monkeypatch.setattr(market_watch, "Ledger", lambda: pytest.fail("ledger must not be opened"))
    with pytest.raises(ValueError, match="revoked and rotated"):
        await market_watch.sportsbooks("nfl", 1)
