from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from sportsbet.quant import nfl_recent_role_shadow as role
from sportsbet.quant import nfl_stat_only_shadow as candidate
from sportsbet.quant import nfl_stat_only_paper as paper
from sportsbet.quant import nfl_stat_only_audit as audit
from sportsbet.quant.market_baseline import paired_market_baseline
from sportsbet.scan import quotes_from_event
from tests.test_nfl_recent_role_shadow import fixture as role_fixture


def fixture(prop='receptions'):
    payload, data = role_fixture()
    line = 19.5 if prop == 'rec_yds' else 2.5
    market = 'player_reception_yds' if prop == 'rec_yds' else 'player_receptions'
    now = datetime(2026, 10, 4, 0, 1, tzinfo=timezone.utc)
    observed = (now-timedelta(seconds=2)).isoformat()
    start = now+timedelta(days=1)
    event = dict(id='stat-only-test', home_team='Home', away_team='Away',
                 commence_time=start.isoformat(), bookmakers=[dict(key='book',
                 markets=[dict(key=market, last_update=observed,
                 outcomes=[dict(name=side, point=line, price=-110,
                                description=payload['player']) for side in ('Over', 'Under')])])])
    quotes = quotes_from_event(event, 'nfl')
    quote = next(q for q in quotes if q.side == 'Over')
    payload.update(game_id=event['id'], game_date=start.date().isoformat(),
                   forecast_cutoff=start.date().isoformat(), game_start_time=start.isoformat(),
                   prop_type=prop, line=line, quote_time=observed, captured_at=now.isoformat(),
                   model_mean_stat=round(3600/33, 2) if prop == 'rec_yds' else round(90/33, 2),
                   model_generated_at=now.isoformat(), sportsbook=quote.sportsbook,
                   american_odds=quote.price, quote_source_provider=quote.source_provider,
                   quote_source_sha256=quote.source_sha256,
                   quote_source_record_sha256=quote.source_record_sha256,
                   **paired_market_baseline(quote, quotes))
    payload['availability']['captured_at'] = now.isoformat()
    payload['history_observed_before'] = observed
    data.update(cutoff=payload['game_date'], observed_before=observed, observed_at=observed)
    proof = role.shadow_record(payload, data)
    assert proof['status'] == 'predicted', proof
    payload['role_history_shadow'] = proof
    payload['role_history_shadow_recorded_at'] = (now+timedelta(seconds=1)).isoformat()
    return payload


@pytest.mark.parametrize('prop', ['receptions', 'rec_yds'])
def test_corrected_role_proof_produces_replayable_untraded_prediction(prop):
    payload = fixture(prop)
    original = deepcopy(payload)
    record = candidate.shadow_record(payload)
    assert record['status'] == 'predicted', record
    assert 0 < record['probability'] < 1
    assert payload == original and payload['accepted'] is False
    with_shadow = payload | dict(stat_only_shadow=record,
                                 stat_only_shadow_recorded_at=(
                                     datetime.fromisoformat(payload['captured_at'])
                                     +timedelta(seconds=2)).isoformat())
    assert candidate.verified_recorded_shadow_probability(with_shadow) == record['probability']
    result = audit.report_stat_only([with_shadow | {'prediction_id': 'one'}])
    assert result['markets'][prop]['counts']['valid_predictions'] == 1
    assert result['markets'][prop]['counts']['pending'] == 1
    assert result['promote'] is False and result['edge_established'] is False


@pytest.mark.parametrize('fault', ['changed_quote', 'changed_role', 'late_role',
                                   'lower_line', 'old_capture', 'changed_probability'])
def test_noncausal_or_mismatched_input_abstains(fault):
    payload = fixture()
    record = candidate.shadow_record(payload)
    if fault == 'changed_quote':
        payload['quote_source_record_sha256'] = '0'*64
    elif fault == 'changed_role':
        payload['role_history_shadow']['probability'] = .5
    elif fault == 'late_role':
        payload['role_history_shadow_recorded_at'] = payload['game_start_time']
    elif fault == 'lower_line':
        payload['line'] = .5
    elif fault == 'old_capture':
        payload['captured_at'] = '2026-10-03T23:59:00+00:00'
    else:
        payload['model_probability'] = .5
    assert candidate.shadow_record(payload)['status'] == 'unavailable'
    assert candidate.verified_shadow_probability(payload | {'stat_only_shadow': record}) is None


def test_candidate_tampering_and_late_server_receipt_fail_closed():
    payload = fixture()
    record = candidate.shadow_record(payload)
    record['probability'] = .99
    assert candidate.verified_shadow_probability(payload | {'stat_only_shadow': record}) is None
    record = candidate.shadow_record(payload)
    late = payload | dict(stat_only_shadow=record,
                          stat_only_shadow_recorded_at=payload['game_start_time'])
    assert candidate.verified_recorded_shadow_probability(late) is None


def test_paper_audit_blocks_invalid_shadow_receipts_instead_of_dropping_them():
    payload = fixture()
    recorded = (datetime.fromisoformat(payload['captured_at'])
                + timedelta(seconds=2)).isoformat()
    original = payload | dict(stat_only_shadow=candidate.shadow_record(payload),
                              stat_only_shadow_recorded_at=recorded,
                              prediction_id='one')
    assert audit._recorded_shadow_is_intact(original)
    for change in ('probability', 'model_version', 'extra_field', 'late_recording'):
        damaged = deepcopy(original)
        if change == 'probability':
            damaged['stat_only_shadow']['probability'] = .99
        elif change == 'model_version':
            damaged['stat_only_shadow']['model_version'] = 'other-version'
        elif change == 'extra_field':
            damaged['stat_only_shadow']['unverified_note'] = 'ignore me'
        else:
            damaged['stat_only_shadow_recorded_at'] = payload['game_start_time']
        result = audit.report_stat_only([damaged])
        market = result['markets']['receptions']
        assert market['counts']['attempts'] == 1
        assert market['counts']['invalid_shadow_receipts'] == 1
        assert market['unavailable_reasons'] == {'invalid_shadow_record': 1}
        assert market['status'] == result['status'] == 'invalid_shadow_receipts'
        assert not result['promote'] and not result['edge_established']
    yards = fixture('rec_yds')
    yards_row = yards | dict(stat_only_shadow=candidate.shadow_record(yards),
                              stat_only_shadow_recorded_at=(
                                  datetime.fromisoformat(yards['captured_at'])
                                  + timedelta(seconds=2)).isoformat(),
                              prediction_id='two')
    combined = audit.report_stat_only([damaged, yards_row])
    assert combined['markets']['rec_yds']['counts']['valid_predictions'] == 1
    assert combined['markets']['rec_yds']['status'] == 'invalid_shadow_receipts'
    assert combined['markets']['receptions']['status'] == 'invalid_shadow_receipts'


def test_replayable_abstention_is_not_a_damaged_shadow_receipt():
    payload = fixture()
    payload['role_history_shadow'] = dict(model_version=role.VERSION,
                                          status='unavailable',
                                          reason='incomplete_participation_history')
    row = payload | dict(stat_only_shadow=candidate.shadow_record(payload),
                         stat_only_shadow_recorded_at=(
                             datetime.fromisoformat(payload['captured_at'])
                             + timedelta(seconds=2)).isoformat())
    assert row['stat_only_shadow']['status'] == 'unavailable'
    assert row['stat_only_shadow']['reason'] == 'role_receipt_unavailable'
    assert audit._recorded_shadow_is_intact(row)
    result = audit.report_stat_only([row | {'prediction_id': 'one'}])
    assert result['markets']['receptions']['counts']['unavailable'] == 1
    assert result['markets']['receptions']['counts']['invalid_shadow_receipts'] == 0
    assert result['status'] == 'collecting'


def test_paper_selection_keeps_both_props_and_earliest_offer():
    payload = fixture()
    later = payload | dict(captured_at=(
        datetime.fromisoformat(payload['captured_at'])+timedelta(seconds=1)).isoformat())
    yards = payload | dict(prop_type='rec_yds')
    rows = [dict(id='z', payload=paper.encode(later)),
            dict(id='b', payload=paper.encode(yards)),
            dict(id='a', payload=paper.encode(payload))]
    selected = paper.earliest(rows)
    assert {(row['prop_type'], row['prediction_id']) for row in selected} == {
        ('receptions', 'a'), ('rec_yds', 'b')}


@pytest.mark.asyncio
async def test_event_capture_reads_only_the_finished_game():
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.transaction.return_value.__aenter__ = AsyncMock(return_value=conn)
    conn.transaction.return_value.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    result = await paper.capture(pool, 'a'*32, event_id='exact-game')
    assert result['status'] == 'no_supported_offers'
    assert conn.fetch.await_args.args == (paper.EVENT_SCAN_SQL, 'a'*32,
                                         paper.MAX_SCAN_ROWS+1, 'exact-game')
    for event in ('', 'x'*101, 7):
        with pytest.raises(ValueError, match='event identity'):
            await paper.capture(pool, 'a'*32, event_id=event)


@pytest.mark.asyncio
async def test_capture_and_server_receipt_use_saved_scan_only(monkeypatch):
    payload = fixture()
    captured = datetime.fromisoformat(payload['captured_at'])
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return captured+timedelta(seconds=2)
    monkeypatch.setattr(paper, 'datetime', Clock)
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[dict(id='prediction', payload=paper.encode(payload))])
    conn.execute = AsyncMock()
    conn.fetchval = AsyncMock(return_value='prediction')
    conn.transaction.return_value.__aenter__ = AsyncMock(return_value=conn)
    conn.transaction.return_value.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    result = await paper.capture(pool, 'a'*32)
    assert result['counts'] == {'attempts': 1, 'predicted': 1, 'recorded': 1}
    args = conn.fetchval.await_args.args
    assert args[0] == paper.INSERT_SQL and args[1] == paper.PROTOCOLS['receptions']
    body = json.loads(args[-2])
    assert body['shadow']['status'] == 'predicted'
    assert args[-1] == paper.digest(args[-2])
    assert conn.fetch.await_args.args == (paper.SCAN_SQL, 'a'*32, paper.MAX_SCAN_ROWS+1)

    receipt_time = captured+timedelta(seconds=2)
    receipt = dict(protocol=paper.PROTOCOLS['receptions'], sport='nfl',
                   game_id=payload['game_id'], player_id=payload['player_id'],
                   prediction_id='prediction', decision_at=payload['captured_at'],
                   valid_until=(datetime.fromisoformat(payload['quote_time'])
                                +timedelta(seconds=300)).isoformat(),
                   recorded_at=receipt_time.isoformat(), payload=args[-2],
                   payload_sha256=args[-1], forecast=paper.encode(payload),
                   outcome=None, outcome_source=None, outcome_ref=None,
                   outcome_observed_at=None, actual_value=None, outcome_evidence=None)
    joined = paper._joined_row(receipt)
    assert candidate.verified_recorded_shadow_probability(joined) == body['shadow']['probability']
    invalid = dict(receipt, forecast=paper.encode(payload | {'model_probability': .1}))
    with pytest.raises(ValueError, match='Invalid paper receipt'):
        paper._joined_row(invalid)
    malformed = paper.encode(json.loads(args[-2]) | {'shadow': []})
    with pytest.raises(ValueError, match='Invalid paper receipt'):
        paper._joined_row(dict(receipt, payload=malformed,
                               payload_sha256=paper.digest(malformed)))
    conn.fetch.return_value = [dict(receipt, payload_sha256='0'*64)]
    report = await paper.report(pool)
    assert report['invalid_paper_receipts'] == 1
    assert report['status'] == 'invalid_paper_receipts'

@pytest.mark.asyncio
async def test_invalid_receipt_blocks_favorable_paper_status(monkeypatch):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[dict(payload='{}')])
    conn.transaction.return_value.__aenter__ = AsyncMock(return_value=conn)
    conn.transaction.return_value.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(paper.audit, 'report_stat_only', lambda rows:
        dict(status='collecting', markets={'receptions': dict(
            status='prospective_probability_support', promote=True)}))
    result = await paper.report(pool)
    assert result['invalid_paper_receipts'] == 1
    assert result['status'] == 'invalid_paper_receipts'
    assert result['markets']['receptions']['status'] == 'invalid_paper_receipts'
    assert result['markets']['receptions']['promote'] is False

def test_frozen_artifact_is_hash_pinned_and_worker_allowlisted():
    from pathlib import Path
    import hashlib
    root = Path(__file__).resolve().parents[1]
    params = root / 'src/sportsbet/quant/nfl_stat_only_params.json'
    assert hashlib.sha256(params.read_bytes()).hexdigest() == candidate.ARTIFACT_SHA256
    assert '!src/sportsbet/quant/nfl_stat_only_params.json' in (
        root / '.dockerignore').read_text(encoding='utf-8').splitlines()
