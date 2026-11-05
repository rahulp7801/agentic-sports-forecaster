"""Bounded worker diagnostics without exception messages, SQL, or credentials."""
from contextlib import contextmanager
import json
import re
import sys


FAILURE_STAGES = {
    'waitlist_provision': frozenset({'arguments', 'context', 'credential_prepare', 'provider_setup',
        'provider_attest', 'provider_team', 'provider_project', 'provider_identity',
        'environment_metadata', 'connect', 'schema_read', 'role_read', 'existing_entry',
        'existing_permissions', 'role_guard', 'password_verifier', 'role_create', 'role_comment',
        'grants', 'new_permissions', 'commit', 'login', 'prepublish_metadata', 'secret_create',
        'postpublish_metadata', 'postpublish_permissions', 'close', 'output'}),
    'hosted_preflight': frozenset({'mode', 'config', 'heads', 'dsn', 'connect',
                                   'schema_read', 'dashboard_read', 'close', 'schema_check', 'output'}),
    'market_watch': frozenset({'publication'}),
    'slate_publication': frozenset({'arguments', 'initialize', 'cache_read', 'collection',
                                  'projection', 'publication', 'publish', 'status',
                                  'receipt_write', 'output'}),
    'daily': frozenset({'initialize', 'histories', 'markets', 'schedules',
                       'settlements', 'props', 'report', 'report_write'}),
    'daily_settlement': frozenset({'ledger', 'settlement', 'publication'}),
    'history_refresh': frozenset({'nba_primary', 'nba_fallback'}),
    'nba_history_validation': frozenset({'crosswalk_season', 'crosswalk_identity',
        'crosswalk_empty', 'crosswalk_target', 'game_finality', 'game_season',
        'game_identity', 'game_time', 'crosswalk_date', 'crosswalk_team',
        'crosswalk_team_conflict', 'boxscore_teams', 'team_abbreviation', 'stat_keys',
        'player_unmapped', 'player_identity', 'counting_stat', 'three_point_stat',
        'playing_time', 'playing_time_bounds', 'boxscore_participants',
        'participant_removal', 'source_https', 'history_gap', 'season_type',
        'event_identity', 'boxscore_window', 'recent_final_history'}),
    'cfb_settlement': frozenset({'history', 'ledger', 'pending_offsets', 'schedules',
                                'settlement', 'predictions', 'publications', 'report_publish'}),
    'published_snapshot_receipt': frozenset({'receipt', 'dsn', 'connect', 'snapshot_read',
                                           'verify', 'close', 'output'}),
}


def error_fields(error: Exception) -> dict:
    name = type(error).__name__
    result = {'error_type': name if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', name) else 'Exception'}
    seen = set()
    current = error
    for _ in range(4):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        code = getattr(current, 'sqlstate', None)
        if isinstance(code, str) and re.fullmatch(r'[0-9A-Z]{5}', code):
            result['sqlstate'] = code
            break
        current = getattr(current, 'orig', None) or getattr(current, '__cause__', None)
    return result


def failure_record(error: Exception, *, operation: str, stage: str,
                   crosswalk_kind: str | None = None,
                   crosswalk_eligibility: tuple[int, int, int, int] | None = None,
                   crosswalk_asset_sha256: str | None = None) -> dict:
    """Allowlisted operational metadata only; never inspect exception text/notes."""
    if (type(operation) is not str or operation not in FAILURE_STAGES
            or type(stage) is not str or stage not in FAILURE_STAGES[operation]):
        raise ValueError('Invalid failure diagnostic scope')
    if crosswalk_kind is not None and (
            operation != 'nba_history_validation' or stage != 'crosswalk_empty'
            or type(crosswalk_kind) is not str
            or crosswalk_kind not in ('schedule', 'player', 'team')):
        raise ValueError('Invalid crosswalk diagnostic kind')
    result = {'schema_version': 1, 'diagnostic_kind': 'operation_failure',
              'operation': operation, 'stage': stage, **error_fields(error)}
    if crosswalk_kind is not None:
        result['crosswalk_kind'] = crosswalk_kind
    if crosswalk_eligibility is not None or crosswalk_asset_sha256 is not None:
        if (operation != 'nba_history_validation' or stage != 'crosswalk_empty' or crosswalk_kind != 'team'
                or type(crosswalk_eligibility) is not tuple or len(crosswalk_eligibility) != 4
                or any(type(value) is not int or not 0 <= value <= 2**53-1 for value in crosswalk_eligibility)
                or type(crosswalk_asset_sha256) is not str
                or re.fullmatch(r'[a-f0-9]{64}', crosswalk_asset_sha256) is None):
            raise ValueError('Invalid team crosswalk diagnostic')
        parsed, method, confidence, required = crosswalk_eligibility
        if not parsed >= method >= confidence >= required == 0:
            raise ValueError('Invalid team crosswalk diagnostic')
        result['crosswalk_eligibility'] = dict(parsed=parsed, exact_method=method,
                                              exact_confidence=confidence, required_fields=required)
        result['crosswalk_asset_sha256'] = crosswalk_asset_sha256
    return result


def emit_failure(error: Exception, *, operation: str, stage: str,
                 crosswalk_kind: str | None = None,
                 crosswalk_eligibility: tuple[int, int, int, int] | None = None,
                 crosswalk_asset_sha256: str | None = None) -> None:
    """Best effort: a diagnostic failure must not replace the original failure."""
    try:
        print(json.dumps(failure_record(error, operation=operation, stage=stage,
                                       crosswalk_kind=crosswalk_kind,
                                       crosswalk_eligibility=crosswalk_eligibility,
                                       crosswalk_asset_sha256=crosswalk_asset_sha256),
                         separators=(',', ':'), allow_nan=False), file=sys.stderr)
    except Exception:
        pass


@contextmanager
def failure_stage(operation: str, stage: str):
    """Re-raise the same exception after emitting bounded stage metadata."""
    try:
        yield
    except Exception as error:
        emit_failure(error, operation=operation, stage=stage)
        raise
