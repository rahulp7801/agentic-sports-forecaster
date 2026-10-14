"""A research pair cannot be manufactured from stale or unbounded prices."""
from datetime import datetime, timedelta, timezone
import copy
from pathlib import Path

import pytest

from sportsbet.quant import kalshi_pair_capture as pair
from sportsbet.quant import kalshi_role_shadow as role
from tests.test_kalshi_role_shadow import fixture


FRESH = datetime(2026, 10, 2, 18, 46, tzinfo=timezone.utc)


def test_bounded_fresh_pair_freezes_both_receipts_without_claiming_edge(monkeypatch):
    archive, _, stats, snaps, identity = fixture()
    monkeypatch.setattr(pair, "build_report", lambda market, cohort, root, *, now:
                        role.predict(market, cohort, stats, snaps, identity, now=now))
    report = pair.capture(archive, Path("unused"), started_at=FRESH,
                          completed_at=FRESH+timedelta(seconds=2))
    assert report["selected_contracts"] == report["forecast_contracts"] == 1
    assert report["market_selection_sha256"] == report["cohort"]["selection_sha256"]
    assert report["forecasts_sha256"] == report["shadow"]["forecasts_sha256"]
    assert float(report["oldest_quote_age_seconds"]) < 300
    assert report["edge_established"] is False and report["qualified_picks"] == 0
    assert report["displayed_midpoint_executable"] is False
    assert pair.unpack(report) == (report["cohort"], report["shadow"])
    changed = copy.deepcopy(report)
    changed["completed_at"] = (FRESH+timedelta(minutes=5)).isoformat()
    with pytest.raises(ValueError, match="chronology"):
        pair.unpack(changed)


def test_stale_market_refused_before_model_load(monkeypatch):
    archive, _, _, _, _ = fixture()
    monkeypatch.setattr(pair, "build_report", lambda *args, **kwargs:
                        pytest.fail("No model load for stale quotes"))
    with pytest.raises(ValueError, match="not fresh"):
        pair.capture(archive, Path("unused"), started_at=FRESH+timedelta(minutes=6))


def test_quote_aging_out_during_model_build_refuses_pair(monkeypatch):
    archive, _, stats, snaps, identity = fixture()
    monkeypatch.setattr(pair, "build_report", lambda market, cohort, root, *, now:
                        role.predict(market, cohort, stats, snaps, identity, now=now))
    with pytest.raises(ValueError, match="timing window"):
        pair.capture(archive, Path("unused"), started_at=FRESH,
                     completed_at=FRESH+timedelta(minutes=5))
    with pytest.raises(ValueError, match="timing window"):
        pair.capture(archive, Path("unused"), started_at=FRESH,
                     completed_at=FRESH+timedelta(seconds=31))
