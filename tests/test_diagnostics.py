from types import SimpleNamespace
from psycopg.errors import ConnectionFailure
from sqlalchemy.exc import OperationalError
from sportsbet.diagnostics import error_fields


def test_wrapped_database_error_exposes_only_sqlstate_and_type():
    original=ConnectionFailure('postgres://secret-password; SQL and private params')
    error=OperationalError('SELECT sensitive',{'key':'secret'},original)
    assert error_fields(error)=={'error_type':'OperationalError','sqlstate':'08006'}
    outer=RuntimeError('private URL');outer.__cause__=error
    assert error_fields(outer)=={'error_type':'RuntimeError','sqlstate':'08006'}


def test_invalid_codes_and_cycles_are_bounded_and_redacted():
    for code in ['secret','08006 secret','0800',None,12345]:
        error=RuntimeError('secret');error.sqlstate=code;error.__cause__=error
        assert error_fields(error)=={'error_type':'RuntimeError'}
    error=RuntimeError('secret');error.orig=SimpleNamespace()
    assert error_fields(error)=={'error_type':'RuntimeError'}
