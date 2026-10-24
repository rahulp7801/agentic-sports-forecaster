from copy import deepcopy
import hashlib
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from sportsbet.ingestion.provenance import stat_row_sha256
from sportsbet.quant import cfb_team_role_shadow as role
from sportsbet.scan import quotes_from_event


def fixture():
    now = datetime(2026, 10, 2, 19, 0, tzinfo=timezone.utc)
    observed = now-timedelta(seconds=3)
    rows = []
    values = [1]*16+[5, 12, 8, 5]
    for index, value in enumerate(values):
        season = 2025 if index < 16 else 2026
        day = date(2025, 9, 1)+timedelta(days=7*index) if index < 16 else date(2026, 9, 1)+timedelta(days=7*(index-16))
        stat = dict(game_id=401000000+index, athlete_id=123, player_name="Player",
                    team_id=1 if index < 16 else 2, season=season, week=index+1 if index < 16 else index-15,
                    game_date=day.isoformat(), is_home=True,
                    team_name="Old" if index < 16 else "New",
                    team_abbreviation="OLD" if index < 16 else "NEW",
                    opponent_id=3, opponent_name="Other", opponent_abbreviation="OTH",
                    passing_yards=None, rushing_yards=None, receiving_yards=value*10,
                    receptions=value)
        rows.append(stat|dict(source_provider="sportsdataverse_espn",
            source_sha256="a"*64, source_record_sha256=stat_row_sha256("cfb", stat),
            source_observed_at=observed.isoformat(), history_policy_version="primary-v1"))
    event = dict(id="cfb-role-test", home_team="New", away_team="Other",
        commence_time="2026-10-02T23:00:00Z",
        bookmakers=[dict(key="book", markets=[dict(key="player_receptions",
            last_update=observed.isoformat(), outcomes=[dict(name="Under", point=5.5,
                price=-110, description="Player")])])])
    quote, = quotes_from_event(event, "cfb")
    over = (sum(value > 5.5 for value in values)+.5)/(len(values)+1)
    payload = dict(player="Player", player_id="123", sport="cfb", game_id=event["id"],
        home_team=event["home_team"], away_team=event["away_team"],
        game_date="2026-10-02", forecast_cutoff="2026-10-02",
        game_start_time=event["commence_time"], prop_type="receptions", line=5.5,
        direction="under", sportsbook=quote.sportsbook, american_odds=quote.price,
        quote_time=observed.isoformat(), quote_source_provider=quote.source_provider,
        quote_source_sha256=quote.source_sha256,
        quote_source_record_sha256=quote.source_record_sha256,
        captured_at=now.isoformat(), model_generated_at=now.isoformat(),
        model_version="empirical-jeffreys-v4-cfb-history-v1",
        history_policy_version="cfb-explicit-receiving-v1",
        history_observed_before=observed.isoformat(), model_sample_size=20,
        model_probability=1-over, model_mean_stat=sum(values)/20, push_probability=0,
        accepted=False, gate_reason="research_fixture", stake_fraction=0,
        availability=dict(status="observed", roster_confirmed=True, player_id="123",
            team="NEW", captured_at=observed.isoformat(),
            roster_source_url="https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams/2/roster",
            roster_source_sha256="b"*64))
    return payload, rows


def test_last_team_candidate_is_sealed_and_replayable():
    payload, rows = fixture()
    original = deepcopy((payload, rows))
    record = role.shadow_record(payload, rows)
    assert record["status"] == "predicted", record
    assert record["current_team_games"] == 4
    assert record["other_team_games"] == 16
    assert record["prior_strength"] == 20
    older_over = .5/17
    candidate_over = (2+20*older_over)/24
    assert record["probability"] == pytest.approx(1-candidate_over)
    assert (payload, rows) == original
    assert role.verified_shadow_probability(payload|{"cfb_team_role_shadow": record}) == record["probability"]
    stored = payload|{"cfb_team_role_shadow": record}
    raw = json.dumps(stored)
    receipt = (datetime.fromisoformat(payload["captured_at"])+timedelta(seconds=1)).isoformat()
    sha = hashlib.sha256(raw.encode()).hexdigest()
    assert role.verified_recorded_shadow_probability(raw, receipt, sha) == record["probability"]
    changed = deepcopy(stored)
    changed["cfb_team_role_shadow"]["probability"] = .99
    changed_raw = json.dumps(changed)
    assert role.verified_recorded_shadow_probability(changed_raw, receipt,
        hashlib.sha256(changed_raw.encode()).hexdigest()) is None


@pytest.mark.parametrize("fault", ["future_source", "wrong_stat", "wrong_hash", "wrong_roster",
                                   "no_team_history", "wrong_baseline", "short", "duplicate",
                                   "stale_quote", "wrong_version"])
def test_invalid_or_late_context_abstains(fault):
    payload, rows = fixture()
    if fault == "future_source": rows[0]["source_observed_at"] = "2026-10-02T19:01:00+00:00"
    elif fault == "wrong_stat": rows[0]["receptions"] = 20
    elif fault == "wrong_hash": rows[0]["source_record_sha256"] = "0"*64
    elif fault == "wrong_roster": payload["availability"]["player_id"] = "999"
    elif fault == "no_team_history": payload["availability"]["team"] = "OTH"
    elif fault == "wrong_baseline": payload["model_probability"] = .5
    elif fault == "short": rows.pop()
    elif fault == "duplicate": rows[1] = rows[0]
    elif fault == "stale_quote": payload["quote_time"] = "2026-10-02T18:00:00+00:00"
    elif fault == "wrong_version": payload["model_version"] = "empirical-jeffreys-v4"
    assert role.shadow_record(payload, rows)["status"] == "unavailable"


def test_corrupt_compressed_input_cannot_replay():
    payload, rows = fixture()
    record = role.shadow_record(payload, rows)
    changed = deepcopy(record)
    changed["inputs"]["sha256"] = "0"*64
    assert role.verified_shadow_probability(payload|{"cfb_team_role_shadow": changed}) is None
    changed = deepcopy(record)
    changed["inputs"]["data"] += "!!!"
    assert role.verified_shadow_probability(payload|{"cfb_team_role_shadow": changed}) is None



@pytest.mark.asyncio
@pytest.mark.parametrize("failed_read", [False, True])
async def test_scan_records_research_only_without_changing_public_signals(tmp_path, monkeypatch, failed_read):
    from decimal import Decimal
    from unittest.mock import AsyncMock, MagicMock
    from sportsbet import scan
    from sportsbet.config import settings
    from sportsbet.graph.models import PropResult
    from sportsbet.ledger import Ledger

    payload, rows = fixture()
    now = datetime.fromisoformat(payload["captured_at"])
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    monkeypatch.setattr(scan, "datetime", Clock)
    monkeypatch.setattr("sportsbet.ledger.datetime", Clock)
    event = dict(id=payload["game_id"], home_team=payload["home_team"],
        away_team=payload["away_team"], commence_time=payload["game_start_time"],
        bookmakers=[dict(key="book", markets=[dict(key="player_receptions",
            last_update=payload["quote_time"], outcomes=[dict(name="Under",
                point=5.5, price=-110, description="Player")])])])
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[dict(normalized_name="player", player_id="123")])
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    monkeypatch.setattr(scan, "write_player_prop_snapshots", AsyncMock())
    graph = MagicMock()
    over = 1-payload["model_probability"]
    graph.ainvoke = AsyncMock(return_value={"prop_result": PropResult(
        true_probability=Decimal(str(over)), sample_size=20,
        mean_stat=Decimal(str(payload["model_mean_stat"])),
        confidence_interval=(Decimal(".01"), Decimal(".4")))})
    monkeypatch.setattr(scan, "create_graph", lambda **kwargs: graph)
    monkeypatch.setattr(scan, "player_availability",
        lambda *args, **kwargs: (payload["availability"]|{
            "subject_status": "available", "teammates": []}, None))
    monkeypatch.setattr(scan, "screened_availability_reports", lambda *args: [])
    monkeypatch.setattr(settings, "history_shadow_enabled", False)
    loader = AsyncMock(side_effect=RuntimeError("private failure")) if failed_read else AsyncMock(
        return_value={("123", "receptions"): rows})
    monkeypatch.setattr(role, "load_inputs", loader)
    baseline = Ledger(tmp_path/"baseline.sqlite", database_url="")
    candidate = Ledger(tmp_path/"candidate.sqlite", database_url="")
    monkeypatch.setattr(settings, "role_history_shadow_enabled", False)
    before = await scan.evaluate_event(pool, event, "cfb", baseline, "same")
    loader.assert_not_awaited()
    monkeypatch.setattr(settings, "role_history_shadow_enabled", True)
    after = await scan.evaluate_event(pool, event, "cfb", candidate, "same")
    assert before["signals"] == after["signals"]
    assert before["coverage"]["counts"] == after["coverage"]["counts"]
    loader.assert_awaited_once()
    assert len(candidate.predictions()) == 1
    recorded, = candidate.predictions()
    if failed_read:
        assert recorded["cfb_team_role_shadow"]["reason"] == "history_read_failed"
    else:
        assert role.verified_shadow_probability(recorded) is not None, recorded["cfb_team_role_shadow"]
    assert recorded["accepted"] is False and recorded["stake_fraction"] == 0
    assert all("cfb_team_role_shadow" not in signal for signal in after["signals"])



def test_private_scorecard_counts_exact_unpriced_pending_offer_without_claim(tmp_path, monkeypatch):
    from sportsbet.ledger import Ledger
    from sportsbet.quant.cfb_team_role_audit import report
    payload, rows = fixture()
    payload["cfb_team_role_shadow"] = role.shadow_record(payload, rows)
    capture = datetime.fromisoformat(payload["captured_at"])+timedelta(seconds=1)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return capture
    monkeypatch.setattr("sportsbet.ledger.datetime", Clock)
    ledger = Ledger(tmp_path/"research.sqlite", database_url="")
    ledger.record("first", payload)
    recorded = ledger.predictions()
    with ledger.connect() as db:
        raw = db.execute("SELECT payload FROM predictions").fetchone()[0]
    receipts = {recorded[0]["prediction_id"]: (
        raw, capture.isoformat(), hashlib.sha256(raw.encode()).hexdigest())}
    result = report(recorded, receipts)
    market = result["markets"]["receptions"]
    assert result["promote"] is False
    assert result["earliest_attempts"] == 1
    assert market["counts"]["verified_candidate"] == 1, market["counts"]
    assert market["counts"]["unpaired_market"] == 1
    assert market["counts"]["paired_decided"] == 0
    assert market["status"] == "insufficient_data"

