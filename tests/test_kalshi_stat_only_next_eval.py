"""Pregame commitment must pin every exact input before venue results."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from sportsbet.quant import kalshi_stat_only_next_eval as next_eval


def test_commitment_rejects_changed_receipt_and_premature_settlement(tmp_path, monkeypatch):
    start = datetime(2026, 10, 8, 0, 0, tzinfo=timezone.utc)
    decided = start-timedelta(hours=2)
    paths = {}
    for name in next_eval.LIMITS:
        path = tmp_path / (name + ('.parquet' if name == 'schedule' else '.json'))
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
    committed = next_eval.commit(paths, sources, now=decided+timedelta(seconds=30))
    assert set(committed['input_sha256']) == set(next_eval.LIMITS) | {'source_manifest'}
    with pytest.raises(ValueError, match='premature'):
        next_eval.evaluate(paths, sources, committed, {}, now=start+timedelta(hours=5))

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
