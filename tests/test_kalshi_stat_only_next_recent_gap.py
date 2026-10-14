"""The motivating slate cannot leak into independently committed validation."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json

import pytest

from sportsbet.quant import kalshi_stat_only_next_recent_gap as gap
from sportsbet.quant import kalshi_stat_only_next_series as primary
from sportsbet.quant import kalshi_pair_capture as capture
from sportsbet.quant import kalshi_market_settlement as venue
from sportsbet.quant.kalshi_market_cohort import digest


def inputs(count=1):
    forecasts, candidates, controls = [], [], []
    for index in range(count):
        ticker, game = f'T{index}', f'G{index}'
        forecasts.append(dict(ticker=ticker, milestone_id=game,
                              gsis_player_id=f'P{index}', model_over_probability='.8'))
        candidates.append(dict(ticker=ticker, milestone_id=game, side='yes',
                               model_win_probability='.8'))
        controls.append(dict(ticker=ticker, prior20_over_probability='.5'))
    return ({'forecasts': forecasts},
            dict(decided_at=gap.POLICY['validation_starts_at'], candidates=candidates,
                 candidates_count=count, candidates_sha256=digest(candidates)),
            {'forecast_rows': controls})


def test_freeze_exact_chosen_side_boundary_and_independent_policy():
    forecast, decisions, control = inputs(3)
    control['forecast_rows'][0]['prior20_over_probability'] = '.75'
    control['forecast_rows'][1]['prior20_over_probability'] = '.75001'
    forecast['forecasts'][2]['model_over_probability'] = '.2'
    decisions['candidates'][2]['side'] = 'no'
    control['forecast_rows'][2]['prior20_over_probability'] = '.25'
    decisions['candidates_sha256'] = digest(decisions['candidates'])
    receipt = gap.freeze(forecast, decisions, control)
    assert len(receipt['evaluation_implementation_sha256']) == 64
    assert receipt['groups'] == {'model_uplift_ge_5pp': ['T0', 'T2'], 'other': ['T1']}
    receipt['policy']['comparators'].clear()
    assert gap.POLICY['comparators'] == ['market', 'strict_prior20']
    decisions['decided_at'] = '2026-10-04T17:00:00+00:00'
    with pytest.raises(ValueError, match='motivating'):
        gap.freeze(forecast, decisions, control)


@pytest.mark.parametrize('change', ['duplicate', 'missing_control', 'model', 'game', 'digest'])
def test_freeze_refuses_altered_scope(change):
    forecast, decisions, control = inputs()
    if change == 'duplicate':
        forecast['forecasts'].append(deepcopy(forecast['forecasts'][0]))
    elif change == 'missing_control':
        control['forecast_rows'].clear()
    elif change == 'model':
        decisions['candidates'][0]['model_win_probability'] = '.9'
        decisions['candidates_sha256'] = digest(decisions['candidates'])
    elif change == 'game':
        decisions['candidates'][0]['milestone_id'] = 'CHANGED'
        decisions['candidates_sha256'] = digest(decisions['candidates'])
    else:
        decisions['candidates_sha256'] = 'changed'
    with pytest.raises(ValueError):
        gap.freeze(forecast, decisions, control)


def setup_series(monkeypatch, count=1, *, remote=True, quote='two_sided_exact', state='venue_verified'):
    forecast, decisions, control = inputs(count)
    values = dict(forecast=forecast, decisions=decisions, control=control, pair={}, market={})
    fixtures = {f'G{i}': ('2026-10-11T17:00:00+00:00', f'A{i}', f'B{i}') for i in range(count)}
    prices = {f'T{i}': (quote, Decimal('.5'), None, None) for i in range(count)}
    states = {f'T{i}': (state, 'yes' if state == 'venue_verified' else None) for i in range(count)}
    cases = [dict(inputs={}, source_dir='.', commitment={'recent_gap_sha256': 'sealed'}, settlements={})]
    admitted = dict(pregame_commitment_sha256=[digest(cases[0]['commitment'])],
                    duplicate_games_excluded=0, independent_selected_games=count,
                    remote_pregame_anchor_verified=remote)
    monkeypatch.setattr(primary, 'aggregate', lambda *args, **kwargs: admitted)
    monkeypatch.setattr(primary.single, 'committed_preflight', lambda *args: (values, {}, prices))
    monkeypatch.setattr(primary, '_fixture_map', lambda *args: fixtures)
    monkeypatch.setattr(capture, 'unpack', lambda *args: ({}, {}))
    monkeypatch.setattr(venue, 'venue_results', lambda *args, **kwargs: ([], states))
    return cases, values, admitted, states


def score(cases):
    return gap.aggregate(cases, now=datetime(2026, 10, 13, tzinfo=timezone.utc))


@pytest.mark.parametrize('count,remote,supported', [(49, True, False), (50, False, False), (50, True, True)])
def test_replication_requires_50_independent_games_and_remote_proof(monkeypatch, count, remote, supported):
    cases, _, _, _ = setup_series(monkeypatch, count, remote=remote)
    report = score(cases)
    group = report['groups']['model_uplift_ge_5pp']
    assert group['paired_independent_games'] == count
    assert group['replication_supported'] is supported
    assert not report['edge_established'] and report['qualified_picks'] == 0
    assert report['roi'] is None and not report['fills_verified']


@pytest.mark.parametrize('label', ['market', 'strict_prior20'])
def test_both_comparators_and_both_cluster_intervals_required(monkeypatch, label):
    cases, _, _, _ = setup_series(monkeypatch, 50)
    original = primary._bounds
    def bounds(rows, name):
        result = original(rows, name)
        if name == label:
            result[f'model_minus_{name}_brier_player_cluster_95'] = ['-.1', '.01']
        return result
    monkeypatch.setattr(primary, '_bounds', bounds)
    assert not score(cases)['groups']['model_uplift_ge_5pp']['replication_supported']


def test_missing_results_remain_in_full_denominator(monkeypatch):
    cases, _, _, states = setup_series(monkeypatch, 50)
    states['T0'] = ('nonbinary', None)
    group = score(cases)['groups']['model_uplift_ge_5pp']
    assert group['frozen_candidates'] == 50 and group['verified_subset_wins'] == 49
    assert group['full_win_rate'] is None and not group['replication_supported']
    assert group['result_states'] == {'nonbinary': 1, 'venue_verified': 49}


def test_first_remote_commitment_retains_missing_quote(monkeypatch):
    cases, values, admitted, _ = setup_series(monkeypatch)
    first = cases[0]
    later = {**first, 'commitment': {'recent_gap_sha256': 'later'}}
    admitted['pregame_commitment_sha256'].append(digest(later['commitment']))
    admitted['duplicate_games_excluded'] = 1
    monkeypatch.setattr(primary.single, 'committed_preflight', lambda _, __, commitment: (
        values, {}, {'T0': ('missing_or_failed', None, None, None)
                     if commitment == first['commitment'] else
                     ('two_sided_exact', Decimal('.5'), None, None)}))
    report = score([later, first])
    group = report['groups']['model_uplift_ge_5pp']
    assert group['frozen_candidates'] == 1 and group['paired_results'] == 0
    assert group['full_win_rate'] == '1'  # Outcome is available; matched price is not.
    assert group['quote_states'] == {'missing_or_failed': 1}
    assert not group['replication_supported']
    assert group['paired_bounds'] == {'market': {}, 'strict_prior20': {}}
    first['commitment'].pop('recent_gap_sha256')
    admitted['pregame_commitment_sha256'][0] = digest(first['commitment'])
    with pytest.raises(ValueError, match='not committed'):
        score([first])


def test_pregame_sibling_receipt_is_hash_bound_and_cannot_be_retrofitted(tmp_path, monkeypatch):
    from sportsbet.quant import kalshi_stat_only_next_eval as single

    forecast, decisions, control = inputs()
    values = dict(forecast=forecast, decisions=decisions, control=control)
    paths = {'pair': tmp_path/'pair.json'}
    path = tmp_path/'recent-gap.json'
    assert single._recent_gap_hash(paths, values) is None
    receipt = gap.freeze(forecast, decisions, control)
    path.write_text(json.dumps(receipt), encoding='utf-8')
    first = single._recent_gap_hash(paths, values)
    assert len(first) == 64
    path.write_text(path.read_text() + ' ', encoding='utf-8')
    assert single._recent_gap_hash(paths, values) != first
    receipt['groups']['model_uplift_ge_5pp'].clear()
    path.write_text(json.dumps(receipt), encoding='utf-8')
    with pytest.raises(ValueError, match='receipt changed'):
        single._recent_gap_hash(paths, values)
    path.write_text(json.dumps(gap.freeze(forecast, decisions, control)), encoding='utf-8')
    monkeypatch.setattr(gap, 'implementation_hash', lambda: 'changed implementation')
    with pytest.raises(ValueError, match='receipt changed'):
        single._recent_gap_hash(paths, values)
