from types import SimpleNamespace
import json
import pytest
from psycopg.errors import ConnectionFailure
from sqlalchemy.exc import OperationalError
from sportsbet.diagnostics import error_fields, failure_record, failure_stage


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


def test_failure_record_has_finite_scope_and_bounded_type_without_private_text():
    error=OperationalError('SELECT private_sql',{'key':'private_parameter'},
                           ConnectionFailure('postgres://private_credential'))
    error.add_note('private_note')
    record=failure_record(error,operation='daily',stage='schedules')
    assert record=={'schema_version':1,'diagnostic_kind':'operation_failure',
        'operation':'daily','stage':'schedules','error_type':'OperationalError','sqlstate':'08006'}
    assert 'private_' not in json.dumps(record)
    for name in ('Injected\n::error::private_type','A'*65,'private type',''):
        unusual=type(name,(Exception,),{})('private_message')
        assert error_fields(unusual)=={'error_type':'Exception'}
    for operation,stage in [('private_scope','schedules'),('daily','private_stage'),
                            ('daily',True),([], 'schedules'),('cfb_settlement','connect')]:
        with pytest.raises(ValueError,match='^Invalid failure diagnostic scope$'):
            failure_record(error,operation=operation,stage=stage)


def test_failure_stage_reraises_exact_error_and_stderr_contains_only_safe_fields(capsys):
    error=RuntimeError('private_message');error.sqlstate='08006 private_suffix'
    error.add_note('private_note')
    with pytest.raises(RuntimeError) as raised:
        with failure_stage('daily','histories'):
            raise error
    assert raised.value is error and error.__notes__==['private_note']
    captured=capsys.readouterr()
    assert captured.out==''
    assert json.loads(captured.err)=={'schema_version':1,'diagnostic_kind':'operation_failure',
        'operation':'daily','stage':'histories','error_type':'RuntimeError'}
    assert 'private_' not in captured.err and 'Traceback' not in captured.err


def test_broken_diagnostic_stream_or_error_attribute_never_replaces_failure(monkeypatch):
    from sportsbet import diagnostics
    class BrokenStream:
        def write(self,value):
            raise OSError('private_stream_failure')
    class BrokenAttribute(RuntimeError):
        @property
        def sqlstate(self):
            raise ValueError('private_attribute_failure')
    for error in (RuntimeError('private_original'),BrokenAttribute('private_original')):
        with monkeypatch.context() as context:
            context.setattr(diagnostics.sys,'stderr',BrokenStream())
            with pytest.raises(RuntimeError) as raised:
                with failure_stage('daily','report'):
                    raise error
            assert raised.value is error
