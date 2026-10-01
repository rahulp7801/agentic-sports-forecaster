from datetime import date
from unittest.mock import MagicMock, patch

from sportsbet.refresh import refresh


def test_manual_refresh_publishes_failure_then_recovery_without_error_text(monkeypatch,capsys):
    import sys
    import pytest
    from sportsbet import refresh as module
    stored=[]
    monkeypatch.setattr(module,'publish_snapshot',lambda key,value:stored.append((key,value)))
    monkeypatch.setattr(sys,'argv',['refresh','--sport','both'])
    def provider(sport,day,backfill):
        if sport=='nfl': raise RuntimeError('private-provider-credential')
        return {'provider':'espn','rows':0}
    monkeypatch.setattr(module,'refresh',provider)
    with pytest.raises(SystemExit) as exc: module.main()
    assert exc.value.code==1
    assert [(key,value['status']) for key,value in stored]==[
        ('refresh:nfl','running'),('refresh:nfl','failed'),('refresh:nba','running'),('refresh:nba','complete')]
    assert 'private-provider-credential' not in capsys.readouterr().out
    assert stored[1][1]['error_type']=='RuntimeError'
    assert stored[-1][1]['coverage']=={'provider':'espn','rows':0}
    monkeypatch.setattr(module,'refresh',lambda *args:{'provider':'nflverse'})
    assert module.refresh_history('nfl',date(2026,9,11))['status']=='complete'


def test_opening_season_backfill_and_daily_refresh():
    engine = MagicMock()
    with patch('sportsbet.refresh.get_sync_engine', return_value=engine), \
         patch('sportsbet.refresh.ingest_games_seasons') as games, \
         patch('sportsbet.refresh.ingest_player_stats_seasons') as nfl, \
         patch('sportsbet.refresh.ingest_snap_counts_seasons') as snaps, \
         patch('sportsbet.refresh.ingest_ngs_seasons',return_value={'assets':[]}) as ngs, \
         patch('sportsbet.refresh.ingest_cfb_gamelogs_season',return_value={'rows':12}) as cfb, \
         patch('sportsbet.refresh.ingest_nba_gamelogs_season') as nba:
        refresh('nfl', date(2026,9,10), backfill=True)
        games.assert_called_once_with([2024,2025,2026], engine)
        nfl.assert_called_once_with([2024,2025,2026], engine)
        snaps.assert_called_once_with([2024,2025,2026], engine)
        ngs.assert_called_once_with([2024,2025,2026], engine)
        refresh('nba', date(2026,10,20), backfill=True)
        assert [call.args[0] for call in nba.call_args_list] == [2025,2026]
        nba.reset_mock()
        refresh('nba', date(2027,1,10))
        nba.assert_called_once_with(2026,engine)
        assert refresh('cfb',date(2026,9,10),backfill=True)=={
            'provider':'sportsdataverse_espn','seasons':[{'rows':12}]*3}
        assert [call.args[0] for call in cfb.call_args_list]==[2024,2025,2026]
        assert engine.dispose.call_count == 4


def test_nba_empty_current_season_retains_honest_coverage():
    engine=MagicMock()
    with patch('sportsbet.refresh.get_sync_engine',return_value=engine), \
         patch('sportsbet.refresh.ingest_nba_gamelogs_season',return_value=0) as ingest:
        result=refresh('nba',date(2026,10,1))
    assert result=={'provider':'nba','seasons':[{'season':2026,'rows':0,'status':'empty'}]}
    ingest.assert_called_once_with(2026,engine)
    engine.dispose.assert_called_once()


def test_nba_primary_parse_failure_uses_existing_bounded_fallback():
    from sportsbet.ingestion.nba_gamelogs import ingest_nba_gamelogs_season
    engine=MagicMock()
    with patch('sportsbet.refresh.get_sync_engine',return_value=engine), \
         patch('sportsbet.ingestion.nba_gamelogs.PlayerGameLogs',
               side_effect=ValueError('invalid provider body')), \
         patch('sportsbet.refresh.ingest_nba_gamelogs_season',
               side_effect=ingest_nba_gamelogs_season), \
         patch('sportsbet.ingestion.nba_espn.refresh_recent',
               return_value={'provider':'espn','games':0,'rows':0}) as fallback:
        assert refresh('nba',date(2026,10,1))=={'provider':'espn','games':0,'rows':0}
    fallback.assert_called_once_with(2026,date(2026,10,1),engine)
    engine.dispose.assert_called_once()
