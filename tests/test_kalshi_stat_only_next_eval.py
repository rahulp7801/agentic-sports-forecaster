"""Pregame commitment must pin every exact input before venue results."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import hashlib

import pytest

from sportsbet.quant import kalshi_stat_only_next_eval as next_eval


def test_committed_replay_uses_retained_schedule_and_refuses_changed_copy(tmp_path, monkeypatch):
    start = datetime(2026, 10, 8, tzinfo=timezone.utc)
    decided = start-timedelta(hours=2)
    root = tmp_path/'cohort'
    root.mkdir()
    paths = {}
    for name in next_eval.LIMITS:
        path = root/(name + ('.parquet' if name == 'schedule' else '.json'))
        path.write_bytes(b'original schedule' if name == 'schedule' else json.dumps({
            'decided_at': decided.isoformat(), 'frozen_model_version': 'fixed',
            'source_model_protocol': 'v4', 'frozen_model_artifact_sha256': 'artifact'}).encode())
        paths[name] = path
    sources = root/'sources'
    sources.mkdir()
    (sources/'source-manifest.json').write_text('{}', encoding='utf-8')
    replayed = []

    def preflight(*args, **kwargs):
        replayed.append(args[-2])
        assert args[-2].read_bytes() == b'original schedule'
        return ({'first_selected_start_at': start.isoformat(),
                 'first_eligible_settlement_at': (start+timedelta(hours=6)).isoformat(),
                 'forecast_sha256': 'forecast', 'candidates_sha256': 'candidates',
                 'paper_candidates': 3, 'paper_games': 2}, {})

    monkeypatch.setattr(next_eval, 'preflight', preflight)
    commitment = next_eval.commit(paths, sources, now=decided)
    assert commitment['input_sha256']['schedule'] == hashlib.sha256(b'original schedule').hexdigest()
    shared = tmp_path/'shared-schedule.parquet'
    shared.write_bytes(b'new schedule')
    supplied = {**paths, 'schedule': shared}
    next_eval.committed_preflight(supplied, sources, commitment)
    shared.unlink()
    next_eval.committed_preflight(supplied, sources, commitment)
    assert replayed[-1] == root/'schedule.parquet'
    assert supplied['schedule'] == shared  # Caller identity is not mutated.

    retained = root/'schedule.parquet'
    retained.write_bytes(b'changed retained schedule')
    shared.write_bytes(b'original schedule')
    previous = len(replayed)
    with pytest.raises(ValueError, match='hash changed'):
        next_eval.committed_preflight(supplied, sources, commitment)
    assert len(replayed) == previous
    retained.unlink()
    retained.mkdir()
    with pytest.raises(ValueError, match='pinned input'):
        next_eval.committed_preflight(supplied, sources, commitment)
    assert len(replayed) == previous


def test_commitment_rejects_changed_receipt_and_premature_settlement(tmp_path, monkeypatch):
    start = datetime(2026, 10, 8, 0, 0, tzinfo=timezone.utc)
    decided = start-timedelta(hours=2)
    paths = {}
    (tmp_path/'shared').mkdir()
    for name in next_eval.LIMITS:
        path = (tmp_path/'shared'/'schedule.parquet' if name == 'schedule'
                else tmp_path/(name+'.json'))
        body = (b'schedule' if name == 'schedule' else json.dumps({
            'decided_at': decided.isoformat(),
            'frozen_model_version': 'fixed',
            'source_model_protocol': 'v4',
            'frozen_model_artifact_sha256': 'artifact'}).encode())
        path.write_bytes(body)
        paths[name] = path
    sources = tmp_path / 'sources'
    sources.mkdir()
    (sources / 'source-manifest.json').write_text('{}', encoding='utf-8')

    def report(*args, **kwargs):
        return ({'first_selected_start_at': start.isoformat(),
                 'first_eligible_settlement_at': (start+timedelta(hours=6)).isoformat(),
                 'forecast_sha256': 'forecast', 'candidates_sha256': 'candidates',
                 'paper_candidates': 3, 'paper_games': 2}, {})

    monkeypatch.setattr(next_eval, 'preflight', report)
    context_dir = tmp_path/'context'
    context_dir.mkdir()
    context_path = context_dir/'receipt.json'
    context_path.write_text(json.dumps({
        'protocol': 'kalshi-nfl-stat-only-next-context-v1',
        'status': 'unavailable', 'reason': 'HTTPStatusError',
        'observed_at': (decided-timedelta(minutes=1)).isoformat(),
        'assets': {}, 'release_metadata_sha256': {},
    }), encoding='utf-8')
    committed = next_eval.commit(paths, sources, now=decided+timedelta(seconds=30))
    assert set(committed['input_sha256']) == set(next_eval.LIMITS) | {'source_manifest'}
    assert committed['context_receipt_sha256']
    assert not (tmp_path/'schedule.parquet').exists()
    # Legacy commitments without a cohort-local schedule remain hash checked.
    next_eval.committed_preflight(paths, sources, committed)
    with pytest.raises(ValueError, match='premature'):
        next_eval.evaluate(paths, sources, committed, {}, now=start+timedelta(hours=5))

    context_path.write_text(context_path.read_text()+" ", encoding='utf-8')
    with pytest.raises(ValueError, match='context receipt changed'):
        next_eval.committed_preflight(paths, sources, committed)

    paths['quotes'].write_text('{"changed": true}', encoding='utf-8')
    with pytest.raises(ValueError, match='hash changed'):
        next_eval.evaluate(paths, sources, committed, {}, now=start+timedelta(hours=7))


def test_commitment_refuses_late_clock(tmp_path, monkeypatch):
    start = datetime(2026, 10, 8, tzinfo=timezone.utc)
    paths = {}
    for name in next_eval.LIMITS:
        path = tmp_path / (name + ('.parquet' if name == 'schedule' else '.json'))
        path.write_bytes(b'schedule' if name == 'schedule' else json.dumps({
            'decided_at': (start-timedelta(hours=2)).isoformat(),
            'frozen_model_version': 'fixed', 'source_model_protocol': 'v4',
            'frozen_model_artifact_sha256': 'artifact'}).encode())
        paths[name] = path
    sources = tmp_path / 'sources'
    sources.mkdir()
    (sources/'source-manifest.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(next_eval, 'preflight', lambda *args, **kwargs: ({
        'first_selected_start_at': start.isoformat()}, {}))
    with pytest.raises(ValueError, match='late'):
        next_eval.commit(paths, sources, now=start)


def test_settled_strict_prior_uses_real_cluster_bounds():
    forecast = {'forecasts': [
        {'ticker': 'ONE', 'milestone_id': 'GAME', 'gsis_player_id': 'PLAYER',
         'model_over_probability': .8},
        {'ticker': 'TWO', 'milestone_id': 'OTHER_GAME', 'gsis_player_id': 'OTHER_PLAYER',
         'model_over_probability': .8},
        {'ticker': 'MISSING', 'milestone_id': 'GAME', 'gsis_player_id': 'OTHER',
         'model_over_probability': .8}]}
    control = {'forecast_rows': [
        {'ticker': 'ONE', 'prior20_over_probability': .5},
        {'ticker': 'TWO', 'prior20_over_probability': .5},
        {'ticker': 'MISSING', 'prior20_over_probability': .5}]}
    prices = {'ONE': ('two_sided_exact', Decimal('.5'), None, None),
              'TWO': ('two_sided_exact', Decimal('.5'), None, None),
              'MISSING': ('missing_or_failed', None, None, None)}
    states = {'ONE': ('venue_verified', 'yes'),
              'TWO': ('venue_verified', 'yes'),
              'MISSING': ('missing', None)}
    report, favorable = next_eval.strict_prior20_scores(
        forecast, control, prices, states)
    assert report['strict_prior20_paired_results'] == 2
    assert report['paired_strict_prior20_brier'] == '0.25'
    assert Decimal(report['strict_prior20_bounds'][
        'model_minus_strict_prior20_brier_game_cluster_95'][1]) < 0
    assert favorable


def test_forward_receipts_cannot_be_added_removed_or_changed_after_commit(tmp_path, monkeypatch):
    from sportsbet.quant import kalshi_stat_only_next_recent_gap as gap
    from sportsbet.quant.kalshi_market_cohort import digest

    decided = datetime(2026, 10, 8, 17, tzinfo=timezone.utc)
    forecast = dict(frozen_model_version='fixed', source_model_protocol='v4',
        frozen_model_artifact_sha256='artifact', forecasts=[dict(ticker='T',
        milestone_id='G', model_over_probability='.8')])
    candidates = [dict(ticker='T', milestone_id='G', side='yes', model_win_probability='.8')]
    decisions = dict(decided_at=decided.isoformat(), candidates=candidates,
                     candidates_count=1, candidates_sha256=digest(candidates))
    control = {'forecast_rows': [dict(ticker='T', prior20_over_probability='.5')]}
    values = dict(forecast=forecast, decisions=decisions, control=control)
    paths = {}
    for name in next_eval.LIMITS:
        path = tmp_path/(name + ('.parquet' if name == 'schedule' else '.json'))
        path.write_bytes(b'schedule' if name == 'schedule' else json.dumps(values.get(name, {})).encode())
        paths[name] = path
    sources = tmp_path/'sources'
    sources.mkdir()
    (sources/'source-manifest.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(next_eval, 'preflight', lambda *args: (dict(
        first_selected_start_at='2026-10-09T00:15:00+00:00', forecast_sha256='forecasts',
        candidates_sha256=decisions['candidates_sha256'], paper_candidates=1, paper_games=1), {}))
    legacy = next_eval.commit(paths, sources, now=decided)
    receipt = tmp_path/'recent-gap.json'
    raw = json.dumps(gap.freeze(forecast, decisions, control))
    receipt.write_text(raw, encoding='utf-8')
    with pytest.raises(ValueError, match='commitment changed'):
        next_eval.committed_preflight(paths, sources, legacy)
    sealed = next_eval.commit(paths, sources, now=decided)
    assert sealed['recent_gap_sha256']
    next_eval.committed_preflight(paths, sources, sealed)
    receipt.write_text(raw+' ', encoding='utf-8')
    with pytest.raises(ValueError, match='commitment changed'):
        next_eval.committed_preflight(paths, sources, sealed)
    receipt.unlink()
    with pytest.raises(ValueError, match='commitment changed'):
        next_eval.committed_preflight(paths, sources, sealed)
    next_eval.committed_preflight(paths, sources, legacy)

    from sportsbet.quant import kalshi_stat_only_source_receiving as receiving
    checked_at = decided-timedelta(minutes=1)
    checked = dict(protocol=receiving.VERSION, observed_at=checked_at.isoformat(),
                   stats_sha256={'2026': 'original'}, counts_reconciled=True)
    monkeypatch.setattr(receiving, 'verify_files', lambda *args, **kwargs: checked)
    source_receipt = tmp_path/'source-receiving.json'
    source_raw = json.dumps(checked)
    source_receipt.write_text(source_raw, encoding='utf-8')
    with pytest.raises(ValueError, match='receiving-source commitment changed'):
        next_eval.committed_preflight(paths, sources, legacy)
    guarded = next_eval.commit(paths, sources, now=decided)
    assert guarded['receiving_source_sha256']
    next_eval.committed_preflight(paths, sources, guarded)
    source_receipt.write_text(source_raw+' ', encoding='utf-8')
    with pytest.raises(ValueError, match='receiving-source commitment changed'):
        next_eval.committed_preflight(paths, sources, guarded)
    source_receipt.write_text(source_raw, encoding='utf-8')
    monkeypatch.setattr(receiving, 'verify_files', lambda *args, **kwargs: {**checked, 'counts_reconciled': False})
    with pytest.raises(ValueError, match='receiving-source receipt changed'):
        next_eval.committed_preflight(paths, sources, guarded)
    monkeypatch.setattr(receiving, 'verify_files', lambda *args, **kwargs: checked)
    source_receipt.write_text(json.dumps({**checked, 'observed_at': (decided+timedelta(seconds=1)).isoformat()}), encoding='utf-8')
    with pytest.raises(ValueError, match='changed or late'):
        next_eval.commit(paths, sources, now=decided)
    source_receipt.unlink()
    with pytest.raises(ValueError, match='receiving-source commitment changed'):
        next_eval.committed_preflight(paths, sources, guarded)
    next_eval.committed_preflight(paths, sources, legacy)
