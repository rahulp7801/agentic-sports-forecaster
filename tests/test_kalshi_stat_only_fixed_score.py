"""The frozen scorer must never receive a premature or unverified result wrapper."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sportsbet.quant import kalshi_stat_only_fixed_score as handoff


def test_early_scoring_cannot_open_settlement(monkeypatch):
    monkeypatch.setattr(handoff.frozen, "_pinned", lambda *args: {})
    monkeypatch.setattr(handoff.frozen, "preflight", lambda *args: (
        {"first_eligible_settlement_at": "2026-10-06T06:15:00+00:00"}, {}))
    monkeypatch.setattr(handoff, "_input", lambda *args: pytest.fail("Early result file read"))
    with pytest.raises(ValueError, match="premature"):
        handoff.score(Path("unused"), now=datetime(2026, 10, 5, tzinfo=timezone.utc))


def test_changed_wrapper_never_reaches_frozen_scorer(monkeypatch):
    monkeypatch.setattr(handoff.frozen, "_pinned", lambda *args: {})
    monkeypatch.setattr(handoff.frozen, "preflight", lambda *args: (
        {"first_eligible_settlement_at": "2026-10-06T06:15:00+00:00"}, {}))
    monkeypatch.setattr(handoff, "_input", lambda *args: ({"changed": True}, "a" * 64))
    monkeypatch.setattr(handoff.frozen, "evaluate", lambda *args, **kwargs: pytest.fail("Invalid wrapper scored"))
    with pytest.raises(ValueError, match="wrapper"):
        handoff.score(Path("unused"), now=datetime(2026, 10, 6, 14, 15, tzinfo=timezone.utc))
