from copy import deepcopy
import hashlib
import json
from datetime import datetime, timedelta

import pytest

from sportsbet.quant import cfb_low_sample_shadow as low
from tests.test_cfb_team_role_shadow import fixture


def low_fixture():
    payload, rows = fixture()
    rows = rows[-12:]
    values = [row['receptions'] for row in rows]
    over = (sum(value > payload['line'] for value in values)+.5)/(len(rows)+1)
    payload.update(model_sample_size=len(rows), model_probability=1-over,
                   model_mean_stat=sum(values)/len(rows), gate_reason='insufficient_sample')
    return payload, rows


def test_low_sample_candidate_is_distinct_sealed_and_replayable():
    payload, rows = low_fixture()
    original = deepcopy((payload, rows))
    record = low.shadow_record(payload, rows)
    assert record['status'] == 'predicted', record
    assert record['sample_size'] == 12
    assert record['current_team_games'] == record['recent_team_games'] == 4
    assert record['other_team_games'] == 8
    assert record['prior_strength'] == 8
    pooled = (2+.5)/13
    recent = (2+.5)/5
    assert record['probability'] == pytest.approx(1-(8*pooled+4*recent)/12)
    assert (payload, rows) == original
    stored = payload|{'cfb_low_sample_shadow': record}
    assert low.verified_shadow_probability(stored) == record['probability']
    raw = json.dumps(stored)
    receipt = (datetime.fromisoformat(payload['captured_at'])+timedelta(seconds=1)).isoformat()
    assert low.verified_recorded_shadow_probability(
        raw, receipt, hashlib.sha256(raw.encode()).hexdigest()) == record['probability']
    changed = deepcopy(stored)
    changed['cfb_low_sample_shadow']['probability'] = .99
    changed_raw = json.dumps(changed)
    assert low.verified_recorded_shadow_probability(changed_raw, receipt,
        hashlib.sha256(changed_raw.encode()).hexdigest()) is None


@pytest.mark.parametrize('fault', ['future_source', 'wrong_stat', 'wrong_hash',
    'wrong_roster', 'wrong_baseline', 'short', 'duplicate', 'stale_quote',
    'wrong_version', 'pre_frozen', 'wrong_current_team'])
def test_low_sample_invalid_context_abstains(fault):
    payload, rows = low_fixture()
    if fault == 'future_source': rows[0]['source_observed_at'] = '2026-10-02T19:01:00+00:00'
    elif fault == 'wrong_stat': rows[0]['receptions'] = 20
    elif fault == 'wrong_hash': rows[0]['source_record_sha256'] = '0'*64
    elif fault == 'wrong_roster': payload['availability']['player_id'] = '999'
    elif fault == 'wrong_baseline': payload['model_probability'] = .5
    elif fault == 'short': rows[:] = rows[:3]
    elif fault == 'duplicate': rows[1] = rows[0]
    elif fault == 'stale_quote': payload['quote_time'] = '2026-10-02T18:00:00+00:00'
    elif fault == 'wrong_version': payload['model_version'] = 'empirical-jeffreys-v4'
    elif fault == 'pre_frozen': payload['captured_at'] = '2026-10-02T07:59:59+00:00'
    elif fault == 'wrong_current_team': payload['availability']['team'] = 'OTH'
    assert low.shadow_record(payload, rows)['status'] == 'unavailable'


async def test_scan_records_low_sample_research_without_changing_public_picks(tmp_path, monkeypatch):
    from decimal import Decimal
    from unittest.mock import AsyncMock, MagicMock
    from sportsbet import scan
    from sportsbet.config import settings
    from sportsbet.graph.models import PropResult
    from sportsbet.ledger import Ledger
    from sportsbet.quant import cfb_team_role_shadow as role

    payload, rows = low_fixture()
    now = datetime.fromisoformat(payload['captured_at'])
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    monkeypatch.setattr(scan, 'datetime', Clock)
    monkeypatch.setattr('sportsbet.ledger.datetime', Clock)
    event = dict(id=payload['game_id'], home_team=payload['home_team'],
        away_team=payload['away_team'], commence_time=payload['game_start_time'],
        bookmakers=[dict(key='book', markets=[dict(key='player_receptions',
            last_update=payload['quote_time'], outcomes=[dict(name='Under',
                point=5.5, price=-110, description='Player')])])])
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[dict(normalized_name='player', player_id='123')])
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    monkeypatch.setattr(scan, 'write_player_prop_snapshots', AsyncMock())
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value={'prop_result': PropResult(
        true_probability=Decimal(str(1-payload['model_probability'])),
        sample_size=12, mean_stat=Decimal(str(payload['model_mean_stat'])),
        confidence_interval=(Decimal('.01'), Decimal('.4')))})
    monkeypatch.setattr(scan, 'create_graph', lambda **kwargs: graph)
    monkeypatch.setattr(scan, 'player_availability',
        lambda *args, **kwargs: (payload['availability']|{
            'subject_status': 'available', 'teammates': []}, None))
    monkeypatch.setattr(scan, 'screened_availability_reports', lambda *args: [])
    monkeypatch.setattr(settings, 'history_shadow_enabled', False)
    loader = AsyncMock(return_value={('123', 'receptions'): rows})
    monkeypatch.setattr(role, 'load_inputs', loader)
    baseline = Ledger(tmp_path/'baseline.sqlite', database_url='')
    candidate = Ledger(tmp_path/'candidate.sqlite', database_url='')
    monkeypatch.setattr(settings, 'role_history_shadow_enabled', False)
    before = await scan.evaluate_event(pool, event, 'cfb', baseline, 'same')
    loader.assert_not_awaited()
    monkeypatch.setattr(settings, 'role_history_shadow_enabled', True)
    after = await scan.evaluate_event(pool, event, 'cfb', candidate, 'same')
    assert before['signals'] == after['signals']
    assert before['coverage']['counts'] == after['coverage']['counts']
    loader.assert_awaited_once()
    recorded, = candidate.predictions()
    assert role.verified_shadow_probability(recorded) is None
    assert low.verified_shadow_probability(recorded) is not None
    assert recorded['accepted'] is False and recorded['stake_fraction'] == 0
    assert after['coverage']['cfb_low_sample_shadow']['inference_counts'] == {'predicted': 1}
    assert all('cfb_low_sample_shadow' not in signal for signal in after['signals'])


def test_private_audit_keeps_unpaired_and_pending_separate(tmp_path, monkeypatch):
    from sportsbet.ledger import Ledger
    from sportsbet.quant.cfb_low_sample_audit import report
    payload, rows = low_fixture()
    payload['cfb_low_sample_shadow'] = low.shadow_record(payload, rows)
    capture = datetime.fromisoformat(payload['captured_at'])+timedelta(seconds=1)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return capture
    monkeypatch.setattr('sportsbet.ledger.datetime', Clock)
    ledger = Ledger(tmp_path/'research.sqlite', database_url='')
    ledger.record('first', payload)
    recorded = ledger.predictions()
    with ledger.connect() as db:
        raw = db.execute('SELECT payload FROM predictions').fetchone()[0]
    receipts = {recorded[0]['prediction_id']: (
        raw, capture.isoformat(), hashlib.sha256(raw.encode()).hexdigest())}
    result = report(recorded, receipts)
    market = result['markets']['receptions']
    assert result['promote'] is False
    assert result['earliest_attempts'] == 1
    assert market['counts']['verified_candidate'] == 1, market['counts']
    assert market['counts']['unpaired_market'] == 1
    assert market['counts']['paired_decided'] == 0
    assert market['status'] == 'insufficient_data'
