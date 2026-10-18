import json
import sys
import pytest

from sportsbet import daily


def test_daily_cli_writes_a_clean_machine_readable_report(monkeypatch,tmp_path,capsys):
    report={'status':'observed','mode':'public_daily','execution_ready':False}

    async def run(*args):
        print('collector progress that must not enter the report file')
        return report

    output=tmp_path/'nested'/'report.json'
    monkeypatch.setattr(daily,'run',run)
    monkeypatch.setattr(sys,'argv',['daily','--mode','public_daily','--report-output',str(output)])
    daily.main()

    assert json.loads(output.read_text(encoding='utf-8'))==report
    assert 'collector progress' in capsys.readouterr().out
    assert not output.with_name('report.json.tmp').exists()


def test_daily_cli_all_includes_cfb_only_for_paid_modes(monkeypatch):
    captured=[]
    async def run(*args):
        captured.append(args)
        return {'status':'complete'}
    monkeypatch.setattr(daily,'run',run)
    monkeypatch.setattr(sys,'argv',['daily','--sport','all','--mode','daily'])
    daily.main()
    assert captured==[(['nfl','nba','cfb'],'daily',20)]


def test_daily_cli_preserves_failed_exit_and_does_not_write_a_success_report(monkeypatch,tmp_path,capsys):
    from psycopg.errors import ConnectionFailure
    from sqlalchemy.exc import OperationalError
    failure=OperationalError('SELECT private_sql',{},ConnectionFailure('postgres://private_credential'))
    async def fail(state):
        raise failure
    async def run(*args):
        return await daily._diagnosed_node(fail,'schedules')({})
    output=tmp_path/'report.json'
    monkeypatch.setattr(daily,'run',run)
    monkeypatch.setattr(sys,'argv',['daily','--mode','public_daily','--report-output',str(output)])
    with pytest.raises(SystemExit) as raised:
        daily.main()
    assert raised.value.code=='Daily pipeline unavailable (OperationalError)'
    assert not output.exists()
    captured=capsys.readouterr()
    assert captured.out==''
    assert json.loads(captured.err)['stage']=='schedules'
    assert 'private_' not in captured.err


def test_report_write_failure_is_diagnosed_without_changing_exit(monkeypatch,tmp_path,capsys):
    async def run(*args):
        return {'status':'observed'}
    def write(*args):
        raise OSError('private_path')
    monkeypatch.setattr(daily,'run',run)
    monkeypatch.setattr(daily,'_write_report',write)
    monkeypatch.setattr(sys,'argv',['daily','--mode','public_monitor','--report-output',str(tmp_path/'report.json')])
    with pytest.raises(SystemExit) as raised:
        daily.main()
    assert raised.value.code=='Daily pipeline unavailable (OSError)'
    assert json.loads(capsys.readouterr().err)['stage']=='report_write'
