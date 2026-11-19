"""Profile refusal diagnostics describe only the presentation guard that failed."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from unittest.mock import Mock

import pytest

from sportsbet import diagnostics
from sportsbet import player_profiles as profiles


CANARY = 'PRIVATE_ATHLETE_TEAM_EVENT_TOKEN'
NOW = datetime(2026, 11, 19, 23, 0, tzinfo=timezone.utc)


class StringSubclass(str):
    pass


def evidence():
    return dict(status='observed', player_id='123', player_image_url='https://private.example/' + CANARY,
                team='BUF', captured_at=NOW.isoformat(), roster_source_url='https://private.example/' + CANARY,
                roster_source_sha256='a' * 64, subject_status=CANARY)


def context():
    return dict(teams=[dict(abbreviation='BUF', name='Buffalo Bills')], private_payload=CANARY)


def refused(case):
    result = evidence()
    expected_team = None
    if case == 'availability_not_observed':
        result['status'] = 'unavailable'
    elif case == 'player_id_missing':
        result.pop('player_id')
    elif case == 'image_missing':
        result.pop('player_image_url')
    elif case == 'expected_team_mismatch':
        result['team'] = 'NYJ'
        expected_team = ('BUF', 'Buffalo Bills')
    return result, expected_team


@pytest.mark.parametrize('sport', ['nfl', 'nba'])
@pytest.mark.parametrize('reason', sorted(diagnostics.PROFILE_UNAVAILABLE_REASONS))
def test_opt_in_rejection_is_fixed_redacted_and_uses_one_existing_availability_evaluation(monkeypatch, capsys, reason, sport):
    data = context()
    result, expected_team = refused(reason)
    original = deepcopy((data, result))
    read = Mock(return_value=(result, CANARY))
    monkeypatch.setattr(profiles, 'player_availability', read)

    assert profiles.profile(data, CANARY, '00-0000001', NOW, sport=sport,
                            expected_team=expected_team, diagnostics=True) is None

    read.assert_called_once_with(data, CANARY, NOW, player_id='00-0000001', sport=sport)
    assert (data, result) == original
    captured = capsys.readouterr()
    assert captured.out == ''
    assert json.loads(captured.err) == dict(schema_version=1, diagnostic_kind='profile_unavailable',
                                           operation='player_profiles', sport=sport, reason=reason)
    assert CANARY not in captured.err
    assert not any(value in captured.err for value in ('https://', '123', '00-0000001', NOW.isoformat(), 'a' * 64))


@pytest.mark.parametrize('reason', sorted(diagnostics.PROFILE_UNAVAILABLE_REASONS))
def test_default_rejection_remains_silent_and_preserves_inputs(monkeypatch, capsys, reason):
    data = context()
    result, expected_team = refused(reason)
    original = deepcopy((data, result))
    read = Mock(return_value=(result, CANARY))
    monkeypatch.setattr(profiles, 'player_availability', read)

    assert profiles.profile(data, CANARY, None, NOW, expected_team=expected_team) is None

    read.assert_called_once_with(data, CANARY, NOW, player_id=None, sport='nfl')
    assert (data, result) == original
    assert capsys.readouterr().err == ''


def test_success_stays_silent_and_presentation_result_ignores_forecast_risk_reason(monkeypatch, capsys):
    data, result = context(), evidence()
    original = deepcopy((data, result))
    read = Mock(return_value=(result, 'player_availability_risk'))
    monkeypatch.setattr(profiles, 'player_availability', read)

    default = profiles.profile(data, CANARY, None, NOW, expected_team=('BUF', 'Buffalo Bills'))
    opted_in = profiles.profile(data, CANARY, None, NOW, expected_team=('BUF', 'Buffalo Bills'), diagnostics=True)

    assert default == opted_in and default['player_id'] == '123'
    assert default['captured_at'] == NOW.isoformat()
    assert not {'subject_status', 'gated', 'true_prob', 'diagnostics'} & default.keys()
    assert read.call_count == 2
    assert all(call.args[2] is NOW for call in read.call_args_list)
    assert (data, result) == original
    captured = capsys.readouterr()
    assert captured.out == captured.err == ''


@pytest.mark.parametrize('reason', sorted(diagnostics.PROFILE_UNAVAILABLE_REASONS))
def test_broken_diagnostic_stream_cannot_change_rejection_result(monkeypatch, reason):
    class BrokenStream:
        def write(self, value):
            raise OSError(CANARY)

    result, expected_team = refused(reason)
    monkeypatch.setattr(profiles, 'player_availability', Mock(return_value=(result, CANARY)))
    with monkeypatch.context() as patch:
        patch.setattr(diagnostics.sys, 'stderr', BrokenStream())
        assert profiles.profile(context(), CANARY, None, NOW, expected_team=expected_team, diagnostics=True) is None


@pytest.mark.parametrize('reason', [CANARY, 'image_missing\n' + CANARY, '', None, 1, True,
                                    ['image_missing'], {'reason': 'image_missing'}, StringSubclass('image_missing')])
def test_diagnostic_constructor_rejects_dynamic_or_non_string_values_and_emitter_stays_silent(capsys, reason):
    with pytest.raises(ValueError, match='^Invalid profile unavailable diagnostic$'):
        diagnostics.profile_unavailable_record(reason, sport='nfl')
    diagnostics.emit_profile_unavailable(reason, sport='nfl')
    captured = capsys.readouterr()
    assert captured.out == captured.err == ''


@pytest.mark.parametrize('sport', [CANARY, 'cfb', 'NFL', 'nfl\n' + CANARY, '', None, 1, True, ['nfl'], {'sport': 'nfl'}, StringSubclass('nfl')])
def test_unsafe_or_unsupported_sport_cannot_be_serialized_or_change_profile_outcome(monkeypatch, capsys, sport):
    result, _ = refused('image_missing')
    read = Mock(return_value=(result, CANARY))
    monkeypatch.setattr(profiles, 'player_availability', read)
    with pytest.raises(ValueError, match='^Invalid profile unavailable diagnostic$'):
        diagnostics.profile_unavailable_record('image_missing', sport=sport)
    diagnostics.emit_profile_unavailable('image_missing', sport=sport)
    assert profiles.profile(context(), CANARY, None, NOW, sport=sport, diagnostics=True) is None
    assert read.call_count == 1
    captured = capsys.readouterr()
    assert captured.out == captured.err == ''


@pytest.mark.parametrize('changes,reason', [
    ({'status': 'unavailable', 'player_id': None, 'player_image_url': None, 'team': 'NYJ'}, 'availability_not_observed'),
    ({'player_id': None, 'player_image_url': None, 'team': 'NYJ'}, 'player_id_missing'),
    ({'player_image_url': None, 'team': 'NYJ'}, 'image_missing'),
])
def test_overlapping_refusals_keep_original_first_failed_guard_order(monkeypatch, capsys, changes, reason):
    result = dict(evidence(), **changes)
    read = Mock(return_value=(result, CANARY))
    monkeypatch.setattr(profiles, 'player_availability', read)
    assert profiles.profile(context(), CANARY, None, NOW, expected_team=('BUF', 'Buffalo Bills'), diagnostics=True) is None
    assert read.call_count == 1
    assert json.loads(capsys.readouterr().err)['reason'] == reason
