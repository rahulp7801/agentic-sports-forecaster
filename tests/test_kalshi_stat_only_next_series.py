"""Overlapping later price captures cannot replace the first game attempt."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from sportsbet.quant import kalshi_stat_only_next_series as series


def test_first_pregame_fixture_owns_missing_quote(monkeypatch):
    def values(which):
        first = which == 'first'
        at = '2026-10-08T17:00:00+00:00' if first else '2026-10-10T17:00:00+00:00'
        return ({'pair': {'started_at': at},
                 'market': {'fixture': {'GAME': ('2026-10-11T17:00:00+00:00', 'A', 'B')},
                            'states': {'TICKER': ('venue_verified', 'yes')}},
                 'forecast': {'frozen_model_artifact_sha256': 'same-artifact',
                              'frozen_implementation_sha256': 'same-code',
                              'forecasts': [{'ticker': 'TICKER',
                                  'milestone_id': 'GAME', 'gsis_player_id': 'PLAYER',
                                  'model_over_probability': .8,
                                  'unfitted_prior_probability': .6}]},
                 'control': {'forecast_rows': [{'ticker': 'TICKER',
                     'prior20_over_probability': .55}]},
                 'decisions': {'candidates': []}}, {},
                {'TICKER': ('missing_or_failed', None, None, None) if first else
                    ('two_sided_exact', Decimal('.5'), None, None)})

    monkeypatch.setattr(series.single, 'committed_preflight',
                        lambda inputs, *args: values(inputs['id']))
    monkeypatch.setattr(series.single, 'evaluate', lambda *args, **kwargs: {})
    monkeypatch.setattr(series, 'unpack', lambda pair: (
        {'selections': [{'milestone_id': 'GAME'}]},
        {'protocol': series.role_v4.VERSION}))
    monkeypatch.setattr(series, '_fixture_map', lambda market, cohort: market['fixture'])
    monkeypatch.setattr(series, 'venue_results',
                        lambda market, *args, **kwargs: ([], market['states']))
    cases = [{'inputs': {'id': which}, 'source_dir': '.',
              'commitment': {'which': which}, 'settlements': {},
              'anchor_commit_oid': which, 'anchor_marker_path': 'marker'}
             for which in ('later', 'first')]
    anchors = []
    def verify(commitment, oid, marker):
        anchors.append(oid)
        return {'commit_oid': oid, 'remote_pushed_at':
            '2026-10-08T17:05:00+00:00' if oid == 'first' else
            '2026-10-10T17:05:00+00:00'}
    monkeypatch.setattr(series.remote_anchor, 'verify', verify)
    report = series.aggregate(cases,
        now=datetime(2026, 10, 13, 7, tzinfo=timezone.utc), verify_remote=True)
    assert anchors == ['later', 'first']
    assert report['remote_pregame_anchor_verified']
    assert report['attempted_games'] == 2
    assert report['duplicate_games_excluded'] == 1
    assert report['independent_selected_games'] == 1
    assert report['selected_model_forecasts'] == 1
    assert report['forecast_quote_states'] == {'missing_or_failed': 1}
    assert report['paired_forecasts'] == 0
    assert not report['paired_skill_signal']
    assert not report['probability_support']
    assert not report['edge_established']

    # If server publication order differs from a client-set local timestamp,
    # the earlier remote commitment owns the game.
    monkeypatch.setattr(series.remote_anchor, 'verify',
        lambda commitment, oid, marker: {'commit_oid': oid,
            'remote_pushed_at': '2026-10-10T18:00:00+00:00' if oid == 'first' else
                                '2026-10-10T17:05:00+00:00'})
    reordered = series.aggregate(cases,
        now=datetime(2026, 10, 13, 7, tzinfo=timezone.utc), verify_remote=True)
    assert reordered['forecast_quote_states'] == {'two_sided_exact': 1}
    assert reordered['paired_forecasts'] == 1


def test_private_series_manifest_cannot_read_outside_its_root(tmp_path):
    root = (tmp_path/'private').resolve()
    root.mkdir()
    with pytest.raises(ValueError, match='escapes'):
        series._local(root, '../outside.json')
    with pytest.raises(ValueError, match='relative'):
        series._local(root, str(tmp_path/'outside.json'))
