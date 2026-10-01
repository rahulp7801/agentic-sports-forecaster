from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import json

import pytest
from sportsbet.quant import individual_pick_context_audit as report
from sportsbet.quant import nfl_recent_role_shadow as role
from tests.test_nfl_recent_role_shadow import fixture
from tests.test_model_selection_paper import receipt, rows, NOW


def context_row():
    row, inputs = fixture()
    row['role_history_shadow'] = role.shadow_record(row, inputs)
    row['role_history_shadow_recorded_at'] = (datetime.fromisoformat(row['captured_at']) + timedelta(seconds=1)).isoformat()
    return row


def test_real_v2_inputs_replay_without_reconstructing_missing_history():
    row = context_row(); before = deepcopy(row)
    value = report.context(row, datetime.fromisoformat(row['captured_at']) + timedelta(seconds=2))
    assert value['available'] and value['fresh'] and value['latest_team_matches']
    assert value['current_role_games'] == 3 and value['older_games'] == 30
    assert value['recent_probability'] == pytest.approx(7.5/11)
    assert value['role_probability'] == row['role_history_shadow']['probability']
    assert report.rules(row['model_probability'], value) == {
        'original_75': True, 'recent_agreement_75': False, 'recent_and_current_role_75': False}
    assert row == before


@pytest.mark.parametrize('fault,reason', [
    ('missing', 'missing_current_role_receipt'), ('old', 'missing_current_role_receipt'),
    ('tamper', 'invalid_role_receipt'), ('late', 'context_recorded_after_selection'),
    ('unavailable', 'incomplete_participation_history'), ('bad_reason', 'invalid_role_receipt'),
])
def test_bad_or_late_context_never_qualifies(fault, reason):
    row = context_row(); at = datetime.fromisoformat(row['captured_at']) + timedelta(seconds=2)
    if fault == 'missing': row.pop('role_history_shadow')
    if fault == 'old': row['role_history_shadow']['model_version'] = 'legacy'
    if fault == 'tamper': row['role_history_shadow']['probability'] = .99
    if fault == 'late': at -= timedelta(seconds=2)
    if fault in ('unavailable', 'bad_reason'):
        row['role_history_shadow'] = dict(model_version=role.VERSION, status='unavailable',
            reason='incomplete_participation_history' if fault == 'unavailable' else [])
    value = report.context(row, at)
    assert value == {'available': False, 'reason': reason}
    assert not report.rules(.99, value)['recent_and_current_role_75']


@pytest.mark.parametrize('field,value', [('fresh', False), ('latest_team_matches', False),
    ('current_role_games', 1), ('older_games', 0), ('role_probability', .749999), ('recent_probability', .749999)])
def test_fixed_context_boundaries_do_not_get_relaxed(field, value):
    evidence = dict(available=True, fresh=True, latest_team_matches=True, current_role_games=2,
        older_games=20, role_probability=.75, recent_probability=.75)
    assert all(report.rules(.75, evidence).values())
    assert not any(report.rules(.749999, evidence).values())
    evidence[field] = value
    assert not report.rules(.75, evidence)['recent_and_current_role_75']


def test_runtime_guard_explains_platform_mismatch():
    with patch.object(report.platform, 'system', return_value='Windows'):
        with pytest.raises(ValueError, match='Linux CPython 3.12'): report.require_matching_runtime()


def test_existing_paper_source_audit_is_required_and_duplicates_fail_closed(monkeypatch):
    monkeypatch.setattr(report, 'require_matching_runtime', lambda: None)
    bad = receipt(); bad['payload'] += ' '
    result = report.audit([bad], rows(), NOW+timedelta(minutes=1))
    assert result['status'] == 'invalid_source_evidence' and result['groups'] == {}
    with pytest.raises(ValueError, match='Duplicate'):
        report.audit([receipt()], rows()+rows(), NOW+timedelta(minutes=1))


def test_context_absence_is_reported_without_substituting_a_different_pick(monkeypatch):
    monkeypatch.setattr(report, 'require_matching_runtime', lambda: None)
    selected = receipt(); original = rows(); before = deepcopy((selected, original))
    result = report.audit([selected], original, NOW+timedelta(minutes=1))
    assert result['coverage']['original_selections'] == 1
    assert result['coverage']['unavailable_reasons'] == {'missing_current_role_receipt': 1}
    assert result['selections'][0]['prediction_id'] == selected['prediction_id']
    assert result['selections'][0]['outcome'] is None
    assert result['status'] == 'exploratory_only' and not result['target_verified'] and not result['promote']
    assert (selected, original) == before


def test_false_unverified_outcomes_and_future_authenticated_outcomes_stay_pending(monkeypatch):
    monkeypatch.setattr(report, 'require_matching_runtime', lambda: None)
    values = rows()
    for row in values:
        row.update(outcome=True, outcome_observed_at=(NOW+timedelta(days=4)).isoformat())
    assert report.audit([receipt()], values, NOW+timedelta(days=5))['selections'][0]['outcome'] is None
    monkeypatch.setattr(report.search.frozen.audit, '_verified_outcome', lambda row: row.get('outcome'))
    assert report.audit([receipt()], values, NOW+timedelta(days=3))['selections'][0]['outcome'] is None
    assert report.audit([receipt()], values, NOW+timedelta(days=5))['selections'][0]['outcome'] is True


def test_summaries_keep_pending_picks_and_use_matching_prices():
    entries = [dict(game_id='a', game_start_time=NOW.isoformat(), outcome=True, american_odds=-200,
        probability=.8, market_probability=.7), dict(game_id='b', game_start_time=NOW.isoformat(),
        outcome=False, american_odds=150, probability=.75, market_probability=.5),
        dict(game_id='c', game_start_time=(NOW+timedelta(days=2)).isoformat(), outcome=None)]
    result = report.summarize(entries, NOW+timedelta(days=1))
    assert result['selected'] == 3 and result['pending'] == 1 and result['upcoming'] == 1
    assert result['decided'] == 2 and result['wins'] == 1 and result['win_rate'] == .5
    assert result['flat_stake_roi'] == -.25
    assert result['mean_recorded_probability'] == .775 and result['mean_market_probability'] == .6


def complete_paper_fixture():
    from sportsbet.scan import quotes_from_event
    from sportsbet.quant.market_baseline import paired_market_baseline
    payload, inputs = fixture()
    observed = (NOW-timedelta(seconds=2)).isoformat()
    inputs.update(observed_at=(NOW-timedelta(seconds=1)).isoformat(), observed_before=observed)
    event = dict(id=payload['game_id'], home_team=payload['home_team'], away_team=payload['away_team'],
        commence_time=payload['game_start_time'], bookmakers=[dict(key='book', markets=[dict(
            key='player_receptions', last_update=observed, outcomes=[dict(name=side, point=.5,
                price=-110, description=payload['player']) for side in ('Over', 'Under')])])])
    quotes = quotes_from_event(event, 'nfl'); predictions = []
    for i, quote in enumerate(quotes):
        row = payload | dict(prediction_id=f'fixture-{i}', captured_at=NOW.isoformat(),
            model_generated_at=NOW.isoformat(), quote_time=observed, history_observed_before=observed,
            direction=quote.side.lower(), quote_source_sha256=quote.source_sha256,
            quote_source_record_sha256=quote.source_record_sha256,
            model_probability=payload['model_probability'] if quote.side == 'Over' else 1-payload['model_probability'],
            recommendation_policy_version='confidence-floor-v2', **paired_market_baseline(quote, quotes))
        row['availability'] = payload['availability'] | dict(captured_at=NOW.isoformat())
        row['role_history_shadow'] = role.shadow_record(row, inputs)
        row['role_history_shadow_recorded_at'] = (NOW+timedelta(seconds=1)).isoformat()
        assert row['role_history_shadow']['status'] == 'predicted'
        predictions.append(row)
    source = next(value for value in report.paper.prepare(predictions, 'nfl', NOW+timedelta(seconds=2))
        if value['protocol'] == report.paper.PROTOCOL['policies']['raw_model'])
    source['recorded_at'] = NOW+timedelta(seconds=3)
    return source, predictions


def test_full_original_selection_and_current_receipt_integration(monkeypatch):
    monkeypatch.setattr(report, 'require_matching_runtime', lambda: None)
    source, predictions = complete_paper_fixture()
    before = deepcopy((source, predictions))
    result = report.audit([source], predictions, NOW+timedelta(minutes=1))
    assert result['source_audit']['valid_receipts'] == 1
    assert result['context_comparison_status'] == 'evaluable_exploratory'
    assert result['high_confidence_coverage']['current_context_available'] == 1
    assert result['groups']['original_75']['pending'] == 1
    assert result['groups']['recent_agreement_75']['selected'] == 0
    assert result['selections'][0]['context']['recent_probability'] == pytest.approx(7.5/11)
    assert (source, predictions) == before


def test_missing_high_confidence_context_is_not_reported_as_negative_filter_evidence(monkeypatch):
    monkeypatch.setattr(report, 'require_matching_runtime', lambda: None)
    source, predictions = complete_paper_fixture()
    for row in predictions: row.pop('role_history_shadow')
    result = report.audit([source], predictions, NOW+timedelta(minutes=1))
    assert result['source_audit']['valid_receipts'] == 1
    assert result['context_comparison_status'] == 'not_evaluable_missing_context'
    assert result['high_confidence_coverage'] == dict(selected=1, current_context_available=0,
        unavailable_reasons={'missing_current_role_receipt': 1})
    assert not result['target_verified']
