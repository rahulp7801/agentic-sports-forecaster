from datetime import datetime, timedelta, timezone

from sportsbet.quant import nfl_rushing_role_accuracy_v2 as audit


NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)
BASE = datetime.fromisoformat(audit.PROTOCOL['frozen_at'])


def cohort_rows(count, *, pending=False, games=50):
    receipts = []
    selections = []
    for n in range(count):
        prediction_id = f'p{n:03}'
        receipts.append(dict(sport='nfl', protocol=audit.PROTOCOL['source_policy'],
            prediction_id=prediction_id, recorded_at=(BASE+timedelta(minutes=n)).isoformat()))
        selections.append(dict(prediction_id=prediction_id, game_id=f'g{n%games}',
            game_start_time=(NOW-timedelta(days=1)).isoformat(),
            agreement_75=True, original_75=True, role_probability=.8,
            probability=.8, market_probability=.5, american_odds=-110,
            outcome=None if pending else True))
    return receipts, selections


def run(monkeypatch, receipts, selections):
    monkeypatch.setattr(audit.v1, 'require_matching_runtime', lambda: None)
    monkeypatch.setattr(audit.v1, 'audit', lambda *args: dict(
        status='awaiting_fixed_cohort', source_audit={'invalid_receipts': 0},
        selections=selections, coverage={'unavailable_reasons': {}}))
    monkeypatch.setattr(audit.v1, 'summarize', lambda cohort, now: dict(
        pending=sum(s['outcome'] is None for s in cohort),
        distinct_decided_games=len({s['game_id'] for s in cohort if s['outcome'] is not None}),
        win_rate=1.0 if cohort else None,
        win_rate_game_cluster_95=[.8, 1.] if cohort else None,
        roi_game_cluster_95=[.1, 1.] if cohort else None,
        brier_difference_game_cluster_95=[-.2, -.01] if cohort else None))
    return audit.audit(receipts, [], NOW)


def test_first_fifty_are_fixed_and_later_wins_cannot_change_result(monkeypatch):
    receipts, selections = cohort_rows(60, games=10)
    result = run(monkeypatch, receipts, selections)
    assert result['cohort_closed']
    assert result['cohort_prediction_ids'] == [f'p{n:03}' for n in range(50)]
    assert result['coverage']['excluded_later_eligible'] == 10
    assert result['status'] == 'insufficient_fixed_cohort'
    assert not result['evidence_criteria_met']
    assert not result['target_verified']


def test_pending_fixed_cohort_does_not_pass_even_with_favorable_scores(monkeypatch):
    receipts, selections = cohort_rows(50, pending=True)
    result = run(monkeypatch, receipts, selections)
    assert result['status'] == 'awaiting_cohort_settlement'
    assert not result['evidence_criteria_met']


def test_predeclared_start_and_minimum_keep_early_receipts_out(monkeypatch):
    receipts, selections = cohort_rows(49)
    receipts.insert(0, dict(receipts[0], prediction_id='old',
        recorded_at=(BASE-timedelta(seconds=1)).isoformat()))
    selections.insert(0, dict(selections[0], prediction_id='old'))
    result = run(monkeypatch, receipts, selections)
    assert result['status'] == 'collecting_fixed_cohort'
    assert len(result['cohort_prediction_ids']) == 49
    assert not result['target_verified']
