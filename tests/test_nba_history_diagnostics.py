"""Offline regressions for bounded NBA history failure diagnostics."""
import json
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import httpx
import pytest
import requests
from requests.exceptions import RequestException

from sportsbet import diagnostics
from sportsbet import refresh as refresh_module
from sportsbet.ingestion import nba_espn


@pytest.fixture(autouse=True)
def prohibit_external_io(monkeypatch):
    def unavailable(*args, **kwargs):
        raise AssertionError('External I/O is forbidden in this regression file')

    monkeypatch.setattr(httpx.Client, 'send', unavailable)
    monkeypatch.setattr(requests.sessions.Session, 'request', unavailable)
    monkeypatch.setattr(refresh_module, 'get_sync_engine', unavailable)
    monkeypatch.setattr(refresh_module, 'publish_snapshot', unavailable)


@pytest.fixture
def final_game():
    game = dict(espn_game_id='123', nba_game_id='0022500001', game_date='2026-01-28',
                home_espn_team_id='1', away_espn_team_id='2',
                nba_home_team_id='101', nba_away_team_id='102')
    teams = {str(i): dict(nba_team_id=str(100 + i), nba_team_abbreviation=name)
             for i, name in ((1, 'LAL'), (2, 'BOS'))}
    players = {str(i): dict(nba_player_id=str(1000 + i), nba_player_name=f'Player {i}')
               for i in range(10)}
    keys = ['minutes', 'points', 'rebounds', 'assists', 'steals', 'blocks',
            'threePointFieldGoalsMade-threePointFieldGoalsAttempted']
    boxes = []
    for team in (1, 2):
        athletes = [dict(athlete={'id': str(i), 'displayName': f'Player {i}'},
                          didNotPlay=False, stats=['28:30', '0', '6', '3', '0', '0', '0-1'])
                    for i in range((team - 1) * 5, team * 5)]
        boxes.append(dict(team={'id': str(team)}, statistics=[dict(keys=keys.copy(), athletes=athletes)]))
    data = dict(header=dict(id='123', season={'year': 2026, 'type': 2}, competitions=[dict(
        date='2026-01-29T00:00Z', status={'type': {'completed': True}},
        competitors=[{'id': '1', 'homeAway': 'home'}, {'id': '2', 'homeAway': 'away'}])]),
        boxscore={'players': boxes})
    return data, game, players, teams


def parse_final(fixture):
    data, game, players, teams = fixture
    return nba_espn.parse_game(data, 2025, game, players, teams, 'a' * 64,
                               datetime(2026, 1, 30, tzinfo=timezone.utc))


def records(capsys):
    captured = capsys.readouterr()
    assert captured.out == ''
    return [json.loads(line) for line in captured.err.splitlines()]


def validation_record(stage):
    return dict(schema_version=1, diagnostic_kind='operation_failure',
                operation='nba_history_validation', stage=stage, error_type='ValueError')


@pytest.mark.parametrize('stage,message', [
    ('game_finality', 'Expected a final box score'),
    ('game_season', 'Expected the requested regular season'),
    ('game_identity', 'Box score does not match the NBA game identity'),
    ('game_time', 'Invalid final game timestamp'),
    ('crosswalk_date', 'Crosswalk date mismatch'),
    ('crosswalk_team', 'Crosswalk team mismatch'),
    ('crosswalk_team_conflict', 'Conflicting team crosswalk'),
    ('boxscore_teams', 'Incomplete box-score teams'),
    ('team_abbreviation', 'Invalid NBA team abbreviation'),
    ('stat_keys', 'Duplicate box-score stat keys'),
    ('player_unmapped', 'Participating player has no verified NBA identity'),
    ('player_identity', 'Invalid or duplicate NBA player identity'),
    ('counting_stat', 'Missing or invalid counting stat'),
    ('three_point_stat', 'Invalid three-point stat'),
    ('playing_time', 'Missing or invalid playing time'),
    ('playing_time_bounds', 'Playing time exceeds storage bounds'),
    ('boxscore_participants', 'Incomplete participating-player box score'),
])
def test_boxscore_rejections_keep_base_exception_and_original_guard(final_game, capsys, stage, message):
    data, game, players, teams = final_game
    competition = data['header']['competitions'][0]
    group = data['boxscore']['players'][0]['statistics'][0]
    if stage == 'game_finality': competition['status']['type']['completed'] = False
    elif stage == 'game_season': data['header']['season']['type'] = 3
    elif stage == 'game_identity': data['header']['id'] = '999'
    elif stage == 'game_time': competition['date'] = '2030-01-29T00:00Z'
    elif stage == 'crosswalk_date': game['game_date'] = '2026-01-29'
    elif stage == 'crosswalk_team': game['home_espn_team_id'] = '9'
    elif stage == 'crosswalk_team_conflict': teams['1']['nba_team_id'] = '999'
    elif stage == 'boxscore_teams': data['boxscore']['players'].pop()
    elif stage == 'team_abbreviation': teams['1']['nba_team_abbreviation'] = 'private-team'
    elif stage == 'stat_keys': group['keys'][1] = 'minutes'
    elif stage == 'player_unmapped': del players['0']
    elif stage == 'player_identity': players['0']['nba_player_id'] = players['1']['nba_player_id']
    elif stage == 'counting_stat': group['athletes'][0]['stats'][1] = '--'
    elif stage == 'three_point_stat': group['athletes'][0]['stats'][-1] = '3-2'
    elif stage == 'playing_time': group['athletes'][0]['stats'][0] = '28:90'
    elif stage == 'playing_time_bounds': group['athletes'][0]['stats'][0] = '1000'
    elif stage == 'boxscore_participants': group['athletes'].pop()
    with pytest.raises(ValueError) as raised:
        parse_final(final_game)
    assert type(raised.value) is ValueError
    assert str(raised.value) == message
    assert records(capsys) == [validation_record(stage)]


@pytest.mark.parametrize('stage,message', [
    ('crosswalk_season', 'Crosswalk season mismatch'),
    ('crosswalk_identity', 'Ambiguous crosswalk identity'),
    ('crosswalk_empty', 'No verified crosswalk identities'),
    ('crosswalk_target', 'Crosswalk target has multiple source identities'),
])
def test_crosswalk_failures_remain_strict(capsys, stage, message):
    row = dict(season='2026', source='one', target='100', match_confidence='1', match_method='exact_name')
    rows = [row]
    if stage == 'crosswalk_season': rows = [row | {'season': '2027'}]
    elif stage == 'crosswalk_identity': rows.append(row | {'target': '101'})
    elif stage == 'crosswalk_empty': rows = [row | {'match_confidence': '0.999999999'}]
    elif stage == 'crosswalk_target': rows.append(row | {'source': 'two'})
    with pytest.raises(ValueError) as raised:
        nba_espn.index_rows(rows, 'source', ('target',), 'exact_name', 2026)
    assert type(raised.value) is ValueError and str(raised.value) == message
    assert records(capsys) == [validation_record(stage)]


def test_success_does_not_emit_failure_and_retains_provenance(final_game, capsys):
    rows = parse_final(final_game)
    assert len(rows) == 10 and rows[0]['points'] == 0 and rows[0]['minutes'] == 28.5
    assert rows[0]['game_id'] == '0022500001' and rows[0]['game_date'] == date(2026, 1, 28)
    assert all(row['source_provider'] == 'espn' and row['source_sha256'] == 'a' * 64 for row in rows)
    assert all(len(row['source_record_sha256']) == 64 for row in rows)
    assert records(capsys) == []


def test_participant_removal_still_prevents_stat_and_participation_writes(final_game, monkeypatch, capsys):
    rows = parse_final(final_game)
    engine = MagicMock()
    conn = engine.begin.return_value.__enter__.return_value
    conn.execute.return_value.all.return_value = [(9999, '0022500001')]
    participation_write = MagicMock()
    monkeypatch.setattr(nba_espn, 'store_participation', participation_write)
    with pytest.raises(ValueError) as raised:
        nba_espn.store_rows(engine, rows)
    assert type(raised.value) is ValueError
    assert str(raised.value) == 'Provider removed a previously recorded participant; official reconciliation required'
    assert conn.execute.call_count == 1  # Existing-participant read only; neither INSERT can execute.
    participation_write.assert_not_called()
    assert engine.begin.return_value.__exit__.call_args.args[1] is raised.value
    assert records(capsys) == [validation_record('participant_removal')]


def test_non_https_source_stops_after_one_request_without_archive_or_database(monkeypatch, capsys):
    client = MagicMock()
    response = client.__enter__.return_value.get.return_value
    response.url.scheme = 'http'
    archive = MagicMock()
    store = MagicMock()
    engine = MagicMock()
    monkeypatch.setattr(nba_espn.httpx, 'Client', lambda **kwargs: client)
    monkeypatch.setattr(nba_espn, 'write_archive', archive)
    monkeypatch.setattr(nba_espn, 'store_rows', store)
    with pytest.raises(ValueError) as raised:
        nba_espn.refresh_recent(2025, date(2026, 1, 30), engine)
    assert type(raised.value) is ValueError and str(raised.value) == 'Source requires HTTPS'
    assert client.__enter__.return_value.get.call_count == 1
    engine.connect.assert_not_called()
    engine.begin.assert_not_called()
    archive.assert_not_called()
    store.assert_not_called()
    assert records(capsys) == [validation_record('source_https')]


def setup_refresh(monkeypatch, primary, fallback):
    engine = MagicMock()
    monkeypatch.setattr(refresh_module, 'get_sync_engine', lambda: engine)
    monkeypatch.setattr(refresh_module, 'ingest_nba_gamelogs_season', primary)
    monkeypatch.setattr(nba_espn, 'refresh_recent', fallback)
    return engine


def test_expected_primary_transport_failure_and_successful_fallback_are_silent(monkeypatch, capsys):
    primary = MagicMock(side_effect=RequestException('private provider body'))
    fallback = MagicMock(return_value={'provider': 'espn', 'games': 0, 'rows': 0})
    engine = setup_refresh(monkeypatch, primary, fallback)
    assert refresh_module.refresh('nba', date(2026, 1, 30)) == fallback.return_value
    primary.assert_called_once_with(2025, engine)
    fallback.assert_called_once_with(2025, date(2026, 1, 30), engine)
    engine.dispose.assert_called_once_with()
    assert records(capsys) == []


def test_backfill_transport_failure_is_terminal_without_recent_fallback(monkeypatch, capsys):
    failure = RequestException('private backfill provider URL')
    primary = MagicMock(side_effect=failure)
    fallback = MagicMock()
    engine = setup_refresh(monkeypatch, primary, fallback)
    with pytest.raises(RequestException) as raised:
        refresh_module.refresh('nba', date(2026, 1, 30), backfill=True)
    assert raised.value is failure
    primary.assert_called_once_with(2024, engine)
    fallback.assert_not_called()
    engine.dispose.assert_called_once_with()
    assert records(capsys) == [dict(schema_version=1, diagnostic_kind='operation_failure',
        operation='history_refresh', stage='nba_primary', error_type='RequestException')]


@pytest.mark.parametrize('phase', ['nba_primary', 'nba_fallback'])
def test_terminal_implicit_errors_preserve_identity_and_redact_untrusted_content(monkeypatch, capsys, phase):
    private_text = 'https://private-provider.invalid/?key=secret SELECT private_sql PRIVATE_BODY'
    failure = ValueError(private_text)
    failure.add_note('PRIVATE_NOTE')
    primary = MagicMock(side_effect=failure if phase == 'nba_primary' else RequestException('PRIVATE_TRANSPORT'))
    fallback = MagicMock(side_effect=failure)
    engine = setup_refresh(monkeypatch, primary, fallback)
    with pytest.raises(ValueError) as raised:
        refresh_module.refresh('nba', date(2026, 1, 30))
    assert raised.value is failure and type(raised.value) is ValueError
    assert str(failure) == private_text and failure.__notes__ == ['PRIVATE_NOTE']
    assert primary.call_count == 1 and fallback.call_count == (phase == 'nba_fallback')
    engine.dispose.assert_called_once_with()
    assert records(capsys) == [dict(schema_version=1, diagnostic_kind='operation_failure',
        operation='history_refresh', stage=phase, error_type='ValueError')]


def test_failed_guard_in_fallback_retains_validation_and_terminal_phase(monkeypatch, final_game, capsys):
    final_game[0]['header']['season']['type'] = 3
    primary = MagicMock(side_effect=RequestException('private transport'))
    fallback = MagicMock(side_effect=lambda *args: parse_final(final_game))
    engine = setup_refresh(monkeypatch, primary, fallback)
    with pytest.raises(ValueError, match='^Expected the requested regular season$') as raised:
        refresh_module.refresh('nba', date(2026, 1, 30))
    assert type(raised.value) is ValueError and fallback.call_count == primary.call_count == 1
    engine.dispose.assert_called_once_with()
    assert records(capsys) == [validation_record('game_season'), dict(
        schema_version=1, diagnostic_kind='operation_failure', operation='history_refresh',
        stage='nba_fallback', error_type='ValueError')]


def test_diagnostic_output_failure_cannot_replace_guard_or_skip_disposal(monkeypatch, final_game):
    class BrokenStream:
        def write(self, value):
            raise OSError('private diagnostic stream failure')

    final_game[0]['header']['season']['type'] = 3
    primary = MagicMock(side_effect=RequestException('private transport'))
    fallback = MagicMock(side_effect=lambda *args: parse_final(final_game))
    engine = setup_refresh(monkeypatch, primary, fallback)
    monkeypatch.setattr(diagnostics.sys, 'stderr', BrokenStream())
    with pytest.raises(ValueError) as raised:
        refresh_module.refresh('nba', date(2026, 1, 30))
    assert type(raised.value) is ValueError
    assert str(raised.value) == 'Expected the requested regular season'
    assert primary.call_count == fallback.call_count == 1
    engine.dispose.assert_called_once_with()


def test_refresh_failure_snapshot_does_not_expose_implicit_provider_content(monkeypatch, capsys):
    failure = ValueError('https://private-provider.invalid/?key=PRIVATE_KEY SELECT PRIVATE_SQL PRIVATE_BODY')
    failure.add_note('PRIVATE_NOTE')
    primary = MagicMock(side_effect=failure)
    fallback = MagicMock()
    engine = setup_refresh(monkeypatch, primary, fallback)
    stored = []
    monkeypatch.setattr(refresh_module, 'publish_snapshot', lambda key, value: stored.append((key, value)))
    result = refresh_module.refresh_history('nba', date(2026, 1, 30))
    assert result['status'] == 'failed' and result['error_type'] == 'ValueError'
    assert set(result) == {'status', 'finished_at', 'error_type'}
    assert [(key, value['status']) for key, value in stored] == [
        ('refresh:nba', 'running'), ('refresh:nba', 'failed')]
    assert 'PRIVATE_' not in json.dumps(stored) and 'private-provider' not in json.dumps(stored)
    fallback.assert_not_called()
    engine.dispose.assert_called_once_with()
    assert records(capsys) == [dict(schema_version=1, diagnostic_kind='operation_failure',
        operation='history_refresh', stage='nba_primary', error_type='ValueError')]


@pytest.mark.parametrize('kind', ['schedule', 'player', 'team'])
@pytest.mark.parametrize('rejection', ['empty', 'confidence'])
def test_fallback_empty_crosswalk_identifies_only_table_without_writes(monkeypatch, capsys, kind, rejection):
    sources = {
        'schedule': (
            'season,espn_game_id,nba_game_id,game_date,home_espn_team_id,away_espn_team_id,'
            'nba_home_team_id,nba_away_team_id,match_method,match_confidence\n'
            '2027,123,0022600001,2026-10-29,1,2,101,102,both,1\n'),
        'player': (
            'season,espn_athlete_id,nba_player_id,nba_player_name,match_method,match_confidence\n'
            '2027,1,1000,PRIVATE_PLAYER,exact_name,1\n'),
        'team': (
            'season,espn_team_id,nba_team_id,nba_team_abbreviation,match_method,match_confidence\n'
            '2027,1,101,LAL,exact_name,1\n'),
    }
    sources[kind] = (sources[kind].splitlines()[0] + '\n' if rejection == 'empty'
                     else sources[kind].replace(',1\n', ',0.999999999\n'))
    client = MagicMock()
    session = client.__enter__.return_value

    def response(url):
        table = next(name for name in sources if f'nba_{name}_crosswalk_2027.csv' in url)
        return httpx.Response(200, text=sources[table], request=httpx.Request('GET', url))

    session.get.side_effect = response
    monkeypatch.setattr(nba_espn.httpx, 'Client', lambda **kwargs: client)
    monkeypatch.setattr(nba_espn.time, 'sleep', lambda _: None)
    archive, store = MagicMock(), MagicMock()
    monkeypatch.setattr(nba_espn, 'write_archive', archive)
    monkeypatch.setattr(nba_espn, 'store_rows', store)
    original_validation_error = nba_espn._validation_error
    failures = []

    def capture_error(*args, **kwargs):
        error = original_validation_error(*args, **kwargs)
        failures.append(error)
        return error

    monkeypatch.setattr(nba_espn, '_validation_error', capture_error)
    primary = MagicMock(side_effect=RequestException('PRIVATE_PRIMARY_BODY'))
    fallback = MagicMock(side_effect=nba_espn.refresh_recent)
    engine = setup_refresh(monkeypatch, primary, fallback)
    with pytest.raises(ValueError, match='^No verified crosswalk identities$') as raised:
        refresh_module.refresh('nba', date(2026, 10, 30))
    assert type(raised.value) is ValueError and failures == [raised.value]
    primary.assert_called_once_with(2026, engine)
    fallback.assert_called_once_with(2026, date(2026, 10, 30), engine)
    assert session.get.call_count == 3
    engine.connect.assert_not_called()
    engine.begin.assert_not_called()
    archive.assert_not_called()
    store.assert_not_called()
    engine.dispose.assert_called_once_with()
    assert records(capsys) == [
        validation_record('crosswalk_empty') | {'crosswalk_kind': kind},
        dict(schema_version=1, diagnostic_kind='operation_failure',
             operation='history_refresh', stage='nba_fallback', error_type='ValueError'),
    ]


@pytest.mark.parametrize('kind', ['schedule', 'player', 'team'])
def test_crosswalk_kind_is_finite_scoped_metadata(kind):
    error = ValueError('PRIVATE_NAME /private/path source-sha256')
    error.add_note('PRIVATE_NOTE')
    base = validation_record('crosswalk_empty')
    assert diagnostics.failure_record(error, operation='nba_history_validation',
                                      stage='crosswalk_empty') == base
    assert diagnostics.failure_record(error, operation='nba_history_validation',
                                      stage='crosswalk_empty', crosswalk_kind=kind) == (
                                          base | {'crosswalk_kind': kind})
    for operation, stage in [('daily', 'histories'), ('nba_history_validation', 'crosswalk_season')]:
        with pytest.raises(ValueError, match='^Invalid crosswalk diagnostic kind$'):
            diagnostics.failure_record(error, operation=operation, stage=stage, crosswalk_kind=kind)


@pytest.mark.parametrize('kind', ['', 'PRIVATE_PLAYER', '/private/path', 'a' * 64,
                                'schedule\nPRIVATE_BODY', True, 1, ['schedule']])
def test_crosswalk_kind_rejects_non_enum_metadata(kind):
    with pytest.raises(ValueError, match='^Invalid crosswalk diagnostic kind$'):
        diagnostics.failure_record(ValueError('PRIVATE_BODY'), operation='nba_history_validation',
                                   stage='crosswalk_empty', crosswalk_kind=kind)


def test_crosswalk_kind_does_not_accept_string_subclasses():
    class Kind(str):
        pass

    with pytest.raises(ValueError, match='^Invalid crosswalk diagnostic kind$'):
        diagnostics.failure_record(ValueError('PRIVATE_BODY'), operation='nba_history_validation',
                                   stage='crosswalk_empty', crosswalk_kind=Kind('schedule'))


def test_crosswalk_kind_broken_stream_preserves_original_guard(monkeypatch):
    class BrokenStream:
        def write(self, value):
            raise OSError('PRIVATE_STREAM_FAILURE')

    monkeypatch.setattr(diagnostics.sys, 'stderr', BrokenStream())
    with pytest.raises(ValueError, match='^No verified crosswalk identities$') as raised:
        nba_espn.index_rows([], 'source', ('target',), 'exact_name', 2027, crosswalk_kind='player')
    assert type(raised.value) is ValueError
