"""Keep new NBA source-time forecasts distinct from the frozen v4 population."""
from datetime import datetime, timedelta

import pytest

from sportsbet.ledger import Ledger
from sportsbet.model_contract import MODEL_VERSION
from sportsbet.picks import build_pick_board
from sportsbet.nba_source_asof import (ReleaseLedger, NBA_HISTORY_FROZEN_AT,
    NBA_HISTORY_POLICY, NBA_MODEL_VERSION, forecast_version_valid,
    quote_evidence_valid, history_policy_for, model_version_for)
from tests.test_multisport_edge import forecast


CUTOFF = datetime.fromisoformat(NBA_HISTORY_FROZEN_AT)


def new_forecast(**changes):
    captured = CUTOFF.isoformat()
    return forecast('nba', captured, game_date=CUTOFF.date().isoformat(),
        game_start_time=(CUTOFF + timedelta(days=1)).isoformat(),
        model_version=NBA_MODEL_VERSION,
        history_policy_version=NBA_HISTORY_POLICY,
        history_observed_before=captured, **changes)


def test_nba_source_time_cohort_starts_at_cutoff_and_preserves_v4(tmp_path):
    assert model_version_for('nba', CUTOFF - timedelta(microseconds=1)) == MODEL_VERSION
    assert model_version_for('nba', CUTOFF) == NBA_MODEL_VERSION
    assert history_policy_for('nba') == NBA_HISTORY_POLICY
    p = new_forecast()
    assert forecast_version_valid(p, CUTOFF)
    assert quote_evidence_valid(p)
    assert not forecast_version_valid(p, CUTOFF - timedelta(microseconds=1))
    ledger = ReleaseLedger(tmp_path / 'nba.sqlite')
    ledger.record('old', forecast('nba'))
    before = ledger.report(model_version=MODEL_VERSION, sport='nba')
    ledger.record('new', p)
    after = ledger.report(model_version=MODEL_VERSION, sport='nba')
    assert after.pop('available_model_versions') == [MODEL_VERSION, NBA_MODEL_VERSION]
    assert before.pop('available_model_versions') == [MODEL_VERSION]
    assert after == before


def test_release_ledger_rejects_forged_nba_cutoff_on_write_and_read(tmp_path):
    path = tmp_path / 'nba.sqlite'
    release = ReleaseLedger(path)
    valid = new_forecast()
    valid_id = release.record('valid', valid)
    forged = valid | {'history_observed_before':
        (CUTOFF-timedelta(microseconds=1)).isoformat()}
    with pytest.raises(ValueError, match='NBA source-time'):
        release.record('forged', forged)
    # Simulate a legacy writer that does not know the new model version.
    Ledger(path).record('legacy-writer', forged)
    rows = release.predictions()
    assert [row['prediction_id'] for row in rows] == [valid_id]
    report = release.report(model_version=NBA_MODEL_VERSION, sport='nba')
    assert report['excluded_missing_metadata'] >= 1


def test_new_nba_receipt_reaches_board_only_with_source_policy():
    p = new_forecast() | {
        'history_observed_before': (CUTOFF+timedelta(seconds=10)).isoformat(),
        'model_generated_at': (CUTOFF+timedelta(seconds=20)).isoformat(),
        'captured_at': (CUTOFF+timedelta(minutes=1)).isoformat(),
        'prediction_id': 'a'*64, 'model_sample_size': 40,
        'model_mean_stat': 24.0, 'model_confidence_interval': [.55, .8],
        'gate_reason': 'accepted', 'trade_plan': ['Recorded pregame estimate'],
        'forecast_cutoff': (CUTOFF+timedelta(days=1)).date().isoformat(),
    }
    now = CUTOFF+timedelta(hours=1)
    board = build_pick_board([p], 'nba', now)
    assert len(board['current']) == 1
    assert board['current'][0]['history_policy_version'] == NBA_HISTORY_POLICY
    assert board['current'][0]['history_observed_before'] == p['history_observed_before']
    for changed in ({'history_policy_version': None},
                    {'history_observed_before': (CUTOFF-timedelta(seconds=1)).isoformat()}):
        assert build_pick_board([p | changed], 'nba', now)['current'] == []


@pytest.mark.parametrize('change', [
    {'history_policy_version': None},
    {'history_policy_version': 'other'},
    {'history_observed_before': None},
    {'history_observed_before': (CUTOFF-timedelta(microseconds=1)).isoformat()},
    {'model_generated_at': (CUTOFF-timedelta(microseconds=1)).isoformat()},
    {'model_generated_at': (CUTOFF+timedelta(seconds=1)).isoformat()},
    {'sport': 'nfl'},
])
def test_nba_source_time_forecast_rejects_changed_identity_or_chronology(change):
    assert not quote_evidence_valid(new_forecast() | change)
