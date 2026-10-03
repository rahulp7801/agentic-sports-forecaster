"""A later exact quote is a markout only for the precommitted contract/side."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from sportsbet.quant import kalshi_quote_markout as markout
from tests.test_kalshi_fee_score import setup_pair


def later_archive(original: dict, *, captured: str = "2026-10-03T12:00:00+00:00") -> dict:
    later = copy.deepcopy(original)
    later["evidence"]["captured_at"] = captured
    quote = later["evidence"]["sources"]["kalshi"]["prop_inventory"]["quotes"][0]
    quote["request_started_at"] = "2026-10-03T11:58:00+00:00"
    quote["received_at"] = "2026-10-03T11:59:00+00:00"
    quote["yes_ask"]["cost"] = "0.57"
    quote["no_ask"]["cost"] = "0.47"
    later["summary"]["captured_at"] = captured
    later["summary"]["evidence_sha256"] = hashlib.sha256(json.dumps(
        later["evidence"], sort_keys=True, allow_nan=False).encode()).hexdigest()
    return later


def resign(later: dict) -> None:
    later["summary"]["evidence_sha256"] = hashlib.sha256(json.dumps(
        later["evidence"], sort_keys=True, allow_nan=False).encode()).hexdigest()


def test_exact_later_side_ask_is_markout_not_profit(monkeypatch: pytest.MonkeyPatch):
    pair, original = setup_pair(monkeypatch)
    later = later_archive(original)
    for policy in ("role", "prior20"):
        report = markout.evaluate(pair, original, later, policy=policy)
        assert report["frozen_candidates"] == report["prelock_matched_candidates"] == 1
        assert report["full_candidate_state_counts"] == {"prelock_exact_ask": 1}
        assert report["side_ask_up"] == report["prelock_matched_games"] == 1
        assert report["mean_side_ask_change"] == "0.05"
        assert report["equal_game_mean_side_ask_change"] == "0.05"
        assert report["closing_line_verified"] is False
        assert report["roi"] is None and report["edge_established"] is False


def test_missing_changed_or_locked_quote_stays_in_frozen_denominator(monkeypatch: pytest.MonkeyPatch):
    pair, original = setup_pair(monkeypatch)
    later = later_archive(original)
    quote = later["evidence"]["sources"]["kalshi"]["prop_inventory"]["quotes"][0]
    quote["ticker"] += "X"
    resign(later)
    assert markout.evaluate(pair, original, later)["full_candidate_state_counts"] == {
        "missing_exact_contract": 1}
    later = later_archive(original)
    quote = later["evidence"]["sources"]["kalshi"]["prop_inventory"]["quotes"][0]
    quote["line"] = "4.5"
    resign(later)
    assert markout.evaluate(pair, original, later)["full_candidate_state_counts"] == {
        "identity_changed": 1}
    later = later_archive(original, captured="2026-10-04T16:30:00+00:00")
    quote = later["evidence"]["sources"]["kalshi"]["prop_inventory"]["quotes"][0]
    quote["request_started_at"] = "2026-10-04T16:28:00+00:00"
    quote["received_at"] = "2026-10-04T16:29:00+00:00"
    resign(later)
    report = markout.evaluate(pair, original, later)
    assert report["full_candidate_state_counts"] == {"after_board_lock": 1}
    assert report["prelock_matched_candidates"] == 0
    assert report["mean_side_ask_change"] is None


def test_future_game_and_source_integrity_boundaries(monkeypatch: pytest.MonkeyPatch):
    pair, original = setup_pair(monkeypatch)
    later = later_archive(original)
    later["evidence"]["sources"]["kalshi"]["prop_inventory"]["quotes"][0]["yes_ask"]["cost"] = "0.01"
    with pytest.raises(ValueError, match="integrity"):
        markout.evaluate(pair, original, later)
    later = later_archive(original, captured="2026-10-05T00:00:00+00:00")
    with pytest.raises(ValueError, match="before all games"):
        markout.evaluate(pair, original, later)
    later = later_archive(original, captured="2026-10-02T18:46:02+00:00")
    quote = later["evidence"]["sources"]["kalshi"]["prop_inventory"]["quotes"][0]
    quote["request_started_at"] = "2026-10-02T18:46:00+00:00"
    quote["received_at"] = "2026-10-02T18:46:01+00:00"
    resign(later)
    with pytest.raises(ValueError, match="after decision"):
        markout.evaluate(pair, original, later)
    later = later_archive(original)
    later["evidence"]["captured_at"] = original["evidence"]["captured_at"]
    later["summary"]["captured_at"] = original["evidence"]["captured_at"]
    resign(later)
    with pytest.raises(ValueError, match="after decision"):
        markout.evaluate(pair, original, later)
