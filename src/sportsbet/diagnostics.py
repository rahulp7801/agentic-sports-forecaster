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
    'daily': frozenset({'initialize', 'histories', 'markets', 'schedules',
                       'settlements', 'props', 'report', 'report_write'}),
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


def failure_record(error: Exception, *, operation: str, stage: str) -> dict:
    """Allowlisted operational metadata only; never inspect exception text/notes."""
    if (type(operation) is not str or operation not in FAILURE_STAGES
            or type(stage) is not str or stage not in FAILURE_STAGES[operation]):
        raise ValueError('Invalid failure diagnostic scope')
    return {'schema_version': 1, 'diagnostic_kind': 'operation_failure',
            'operation': operation, 'stage': stage, **error_fields(error)}


def emit_failure(error: Exception, *, operation: str, stage: str) -> None:
    """Best effort: a diagnostic failure must not replace the original failure."""
    try:
        print(json.dumps(failure_record(error, operation=operation, stage=stage),
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
