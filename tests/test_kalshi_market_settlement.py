"""Exact venue-result scoring without retrospective pick selection."""
import copy
from datetime import datetime, timezone
import hashlib
import json

import pytest

from sportsbet.quant import kalshi_market_cohort as market
from sportsbet.quant import kalshi_market_settlement as settlement


START = "2026-10-04T17:00:00+00:00"
TICKER = "KXNFLREC-26OCT04EXAMPLE-PLAYER-4"
PLAYER = "player-1"
TEAM = "team-1"
RULES = {"primary": "Four or more receptions?", "secondary": "Venue-specific participation rule."}
AFTER_GAME = datetime(2026, 10, 5, tzinfo=timezone.utc)


def source():
    quote = dict(ticker=TICKER, milestone_id="game-1", player_target_id=PLAYER,
        team_target_id=TEAM, prop_type="receptions", line="3.5",
        request_started_at="2026-10-02T18:43:20+00:00",
        received_at="2026-10-02T18:43:21+00:00", scheduled_game_start_time=START,
        market_sha256="a"*64, source_page_sha256="b"*64,
        rules_sha256=hashlib.sha256(json.dumps(
            RULES, sort_keys=True, allow_nan=False).encode()).hexdigest(),
        yes_ask={"cost": "0.52", "displayed_size": "10"},
        no_ask={"cost": "0.50", "displayed_size": "8"})
    evidence = dict(schema_version=2, sport="nfl", captured_at="2026-10-02T18:43:24+00:00",
        sources={"kalshi": dict(status="observed", partial_coverage=False,
            targets={TEAM: {"details": {"abbreviation": "PIT"}}},
            games=[{"milestone": {"id": "game-1", "start_date": START,
                                  "details": {"home_team_id": TEAM, "away_team_id": "team-2"}}}],
            prop_inventory=dict(partial_coverage=False,
                coverage=dict(discovery_complete=True, series_expected=4,
                              series_observed=4, structured_quote_markets=1),
                targets={PLAYER: {"player_name": "Example Player", "team_target_id": TEAM}},
                quotes=[quote]))})
    archive = dict(evidence=evidence, summary=dict(sport="nfl", captured_at=evidence["captured_at"],
        evidence_sha256=hashlib.sha256(json.dumps(
            evidence, sort_keys=True, allow_nan=False).encode()).hexdigest()))
    return archive, market.freeze(archive, "2026-10-03T07:29:15+00:00")


def settled(cohort):
    contract = dict(ticker=TICKER, event_ticker=TICKER.rsplit("-", 1)[0],
        status="finalized", result="no", settlement_value_dollars="0.0000",
        settlement_ts="2026-10-04T22:00:00+00:00", market_type="binary",
        notional_value_dollars="1.0000", strike_type="greater", floor_strike=3.5,
        custom_strike=dict(football_player=PLAYER, football_team=TEAM),
        rules_primary=RULES["primary"], rules_secondary=RULES["secondary"])
    evidence = dict(protocol=settlement.VERSION, selection_sha256=cohort["selection_sha256"],
        pages=[dict(tickers=[TICKER], request_started_at="2026-10-04T23:00:00+00:00",
                    received_at="2026-10-04T23:00:01+00:00",
                    body=dict(markets=[contract], cursor=""))])
    return dict(evidence=evidence, evidence_sha256=market.digest(evidence))


def resign(archive):
    archive["evidence_sha256"] = market.digest(archive["evidence"])


def audited(archive, cohort, response):
    return settlement.audit(archive, cohort, response, now=AFTER_GAME)


def test_exact_venue_result_scores_market_baseline_without_edge_claim():
    archive, cohort = source()
    result = audited(archive, cohort, settled(cohort))
    assert result["selected_contracts"] == result["verified_games"] == 1
    assert result["result_counts"] == {"venue_verified": 1}
    assert result["verified_contract_brier"] == "0.2601"
    assert result["equal_verified_game_brier"] == "0.2601"
    assert result["complete"] is True
    assert result["model_forecasts_matched"] == 0
    assert result["roi"] is None and result["edge_established"] is False


def test_missing_or_nonfinal_contract_stays_in_denominator():
    archive, cohort = source()
    response = settled(cohort)
    response["evidence"]["pages"][0]["body"]["markets"] = []
    resign(response)
    report = audited(archive, cohort, response)
    assert report["selected_contracts"] == 1 and report["result_counts"] == {"not_returned": 1}
    assert report["verified_contract_brier"] is None and report["complete"] is False
    response = settled(cohort)
    response["evidence"]["pages"][0]["body"]["markets"][0]["status"] = "open"
    resign(response)
    assert audited(archive, cohort, response)["result_counts"] == {"not_final": 1}


@pytest.mark.parametrize("change", [
    {"custom_strike": {"football_player": "other", "football_team": TEAM}},
    {"custom_strike": {"football_player": PLAYER, "football_team": "other"}},
    {"floor_strike": 4.5},
    {"rules_secondary": "Changed settlement rule"},
    {"settlement_value_dollars": "1.0000"},
    {"settlement_ts": "2026-10-04T16:00:00+00:00"},
    {"settlement_ts": "2026-10-05T00:00:00+00:00"},
])
def test_wrong_identity_rules_or_chronology_cannot_score(change):
    archive, cohort = source()
    response = settled(cohort)
    response["evidence"]["pages"][0]["body"]["markets"][0].update(change)
    resign(response)
    result = audited(archive, cohort, response)
    assert result["result_counts"] == {"invalid_contract_or_settlement": 1}
    assert result["verified_contract_brier"] is None


def test_nonbinary_result_is_excluded_without_zero_imputation():
    archive, cohort = source()
    response = settled(cohort)
    response["evidence"]["pages"][0]["body"]["markets"][0]["result"] = "void"
    resign(response)
    assert audited(archive, cohort, response)["result_counts"] == {"nonbinary_result": 1}


def test_future_response_cannot_be_audited_as_present_evidence():
    archive, cohort = source()
    with pytest.raises(ValueError, match="chronology"):
        settlement.audit(archive, cohort, settled(cohort),
                         now=datetime(2026, 10, 4, 22, tzinfo=timezone.utc))


def test_archive_tamper_duplicate_and_unrequested_contract_fail():
    archive, cohort = source()
    response = settled(cohort)
    response["evidence"]["pages"][0]["body"]["markets"][0]["result"] = "yes"
    with pytest.raises(ValueError, match="integrity"):
        audited(archive, cohort, response)
    response = settled(cohort)
    rows = response["evidence"]["pages"][0]["body"]["markets"]
    rows.append(copy.deepcopy(rows[0]))
    resign(response)
    with pytest.raises(ValueError, match="duplicate"):
        audited(archive, cohort, response)
    rows[-1]["ticker"] = "OTHER"
    resign(response)
    with pytest.raises(ValueError, match="Unexpected"):
        audited(archive, cohort, response)


def test_market_source_or_frozen_selection_change_cannot_score():
    archive, cohort = source()
    changed = copy.deepcopy(cohort)
    changed["selections"][0]["market_midpoint"] = "0.90"
    with pytest.raises(ValueError, match="selection"):
        audited(archive, changed, settled(cohort))
    archive["evidence"]["sources"]["kalshi"]["prop_inventory"]["quotes"][0]["line"] = "4.5"
    with pytest.raises(ValueError, match="integrity"):
        audited(archive, cohort, settled(cohort))


class FakeReader:
    def __init__(self):
        self.calls = []

    async def settled_markets(self, tickers, *, historical):
        self.calls.append((tickers, historical))
        return {"markets": [], "cursor": ""}


@pytest.mark.asyncio
async def test_collector_waits_until_after_every_game_and_uses_only_exact_public_reads():
    archive, cohort = source()
    reader = FakeReader()
    with pytest.raises(ValueError, match="premature"):
        await settlement.collect(archive, cohort, reader,
                                 now=datetime(2026, 10, 4, 21, tzinfo=timezone.utc))
    assert reader.calls == []
    collected = await settlement.collect(archive, cohort, reader,
                                         now=datetime(2026, 10, 5, tzinfo=timezone.utc))
    assert reader.calls == [([TICKER], False)]
    assert collected["evidence_sha256"] == market.digest(collected["evidence"])


def test_provider_failure_remains_explicit_unavailable():
    archive, cohort = source()
    response = settled(cohort)
    page = response["evidence"]["pages"][0]
    del page["body"]
    page["error_type"] = "RuntimeError"
    resign(response)
    result = audited(archive, cohort, response)
    assert result["result_counts"] == {"provider_unavailable": 1}
    assert result["complete"] is False
