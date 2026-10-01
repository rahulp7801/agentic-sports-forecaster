from datetime import datetime, timedelta, timezone

from sportsbet.quant import nfl_receiving_accuracy_v1 as audit

NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)
BASE = datetime.fromisoformat(audit.PROTOCOL['frozen_at'])


def evidence(count=50, *, games=50, pending=False):
    receipts, predictions, selections = [], [], []
    for n in range(count):
        prediction_id = f'p{n:03}'
        stamp = BASE + timedelta(minutes=n)
        receipts.append(dict(prediction_id=prediction_id, sport='nfl',
            protocol=audit.PROTOCOL['original_policy'], recorded_at=(stamp+timedelta(seconds=2)).isoformat()))
        predictions.append(dict(prediction_id=prediction_id, captured_at=stamp.isoformat()))
        selections.append(dict(prediction_id=prediction_id, game_id=f'g{n%games}',
            prop_type='receptions', game_start_time=(NOW-timedelta(days=1)).isoformat(),
            rules={'original_75': True, 'recent_and_current_role_75': True},
            context={'available': True, 'role_probability': .9},
            outcome=None if pending else True, american_odds=100,
            probability=.8, market_probability=.5))
    return receipts, predictions, selections


def run(monkeypatch, receipts, predictions, selections, *, invalid=False):
    monkeypatch.setattr(audit.context, 'require_matching_runtime', lambda: None)
    monkeypatch.setattr(audit.context, 'audit', lambda *args: dict(
        status='invalid_source_evidence' if invalid else 'exploratory_only',
        source_audit={'invalid_receipts': int(invalid)},
        selections=selections, coverage={'unavailable_reasons': {}}))
    return audit.audit(receipts, predictions, NOW)


def test_first_fifty_are_locked_before_later_outcomes_and_use_original_prices(monkeypatch):
    receipts, predictions, selections = evidence(60)
    for item in selections[50:]:
        item['outcome'] = False
    result = run(monkeypatch, receipts, predictions, selections)
    assert result['cohort_prediction_ids'] == [f'p{n:03}' for n in range(50)]
    assert result['coverage']['excluded_later_eligible'] == 10
    assert result['rule']['wins'] == 50 and result['rule']['decided'] == 50
    assert result['rule']['flat_stake_roi'] == 1.0
    assert result['rule']['candidate_minus_market'] < 0
    assert result['rule']['candidate_minus_original'] < 0
    assert result['status'] == 'review_required' and result['evidence_criteria_met']
    assert not result['target_verified'] and not result['promote']


def test_no_winner_substitution_for_missing_context_or_prefreeze_capture(monkeypatch):
    receipts, predictions, selections = evidence(51)
    selections[0]['rules']['recent_and_current_role_75'] = False
    predictions[1]['captured_at'] = (BASE-timedelta(seconds=1)).isoformat()
    result = run(monkeypatch, receipts, predictions, selections)
    assert result['coverage']['original_receiving_selections'] == 50
    assert result['coverage']['eligible_agreements'] == 49
    assert result['cohort_prediction_ids'][0] == 'p002'
    assert result['status'] == 'collecting_fixed_cohort'
    assert not result['evidence_criteria_met']


def test_fixed_cohort_requires_all_settlements_and_independent_games(monkeypatch):
    receipts, predictions, selections = evidence(50, pending=True)
    result = run(monkeypatch, receipts, predictions, selections)
    assert result['status'] == 'awaiting_cohort_settlement'
    assert result['rule']['pending'] == 50 and not result['evidence_criteria_met']
    receipts, predictions, selections = evidence(50, games=10)
    result = run(monkeypatch, receipts, predictions, selections)
    assert result['status'] == 'insufficient_fixed_cohort'
    assert not result['evidence_criteria_met']


def test_invalid_source_receipts_fail_closed(monkeypatch):
    receipts, predictions, selections = evidence(1)
    result = run(monkeypatch, receipts, predictions, selections, invalid=True)
    assert result['status'] == 'invalid_source_evidence'
    assert not result['target_verified'] and 'cohort_prediction_ids' not in result


def test_matching_price_brier_preserves_pending_and_direction_probability():
    entries=[dict(game_id='one',outcome=True,probability=.8,market_probability=.6,
                  context={'role_probability':.9}),
             dict(game_id='two',outcome=None,probability=.8,market_probability=.4,
                  context={'role_probability':.95})]
    values=audit._paired_brier(entries)
    assert abs(values['candidate_minus_market']-(.1**2-.4**2))<1e-12
    assert abs(values['candidate_minus_original']-(.1**2-.2**2))<1e-12
