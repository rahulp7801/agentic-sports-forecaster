"""Refresh the historical game samples used by the scheduled prop worker."""
import argparse
import json
from datetime import date, datetime, timezone
from requests.exceptions import RequestException

from sportsbet.db.connection import get_sync_engine
from sportsbet.dashboard import publish_snapshot
from sportsbet.diagnostics import emit_failure, error_fields, failure_stage
from sportsbet.ingestion.games import ingest_games_seasons
from sportsbet.ingestion.cfb_gamelogs import ingest_cfb_gamelogs_season
from sportsbet.ingestion.nba_gamelogs import ingest_nba_gamelogs_season
from sportsbet.ingestion.player_stats import ingest_player_stats_seasons
from sportsbet.ingestion.snap_counts import ingest_snap_counts_seasons
from sportsbet.ingestion.ngs import ingest_ngs_seasons


def refresh(sport: str, today: date, backfill: bool = False):
    if sport not in ('nba','nfl','cfb'):
        raise ValueError('Unsupported sport')
    boundary=10 if sport=='nba' else 8 if sport=='cfb' else 9
    start = today.year if today.month >= boundary else today.year-1
    # NFL requires multiple seasons to reach the minimum sample; NBA prior season covers opening night.
    years = list(range(start-(2 if sport in ('nfl','cfb') else 1), start+1)) if backfill else [start]
    engine = get_sync_engine()
    ngs: dict = {}
    try:
        if sport == 'nfl':
            ingest_games_seasons(years, engine)
            ingest_player_stats_seasons(years, engine)
            ingest_snap_counts_seasons(years, engine)
            ngs_years=sorted(set(years+[start-1]))
            try:
                ngs=ingest_ngs_seasons(ngs_years,engine)
                ngs['status']='complete'
            except Exception as exc:
                # Optional tracking context cannot make the source-backed base
                # history/model unavailable and does not alter probabilities.
                ngs={'status':'failed','error_type':type(exc).__name__}
        elif sport == 'nba':
            nba_seasons=[]
            for season in years:
                try:
                    rows=ingest_nba_gamelogs_season(season, engine)
                    nba_seasons.append({'season':season,'rows':rows,
                                        'status':'empty' if rows==0 else 'complete'})
                except RequestException as exc:
                    if backfill:
                        emit_failure(exc,operation='history_refresh',stage='nba_primary')
                        raise  # Bounded recent updates cannot substitute for a full backfill.
                    from sportsbet.ingestion.nba_espn import refresh_recent
                    with failure_stage('history_refresh','nba_fallback'):
                        return refresh_recent(season,today,engine)
                except Exception as exc:
                    emit_failure(exc,operation='history_refresh',stage='nba_primary')
                    raise
        else:
            coverage=[ingest_cfb_gamelogs_season(season,engine) for season in years]
            return {'provider':'sportsdataverse_espn','seasons':coverage}
        if sport=='nfl':
            return {'provider':'nflverse','next_gen_stats':ngs}
        return {'provider':'nba','seasons':nba_seasons}
    finally:
        engine.dispose()


def refresh_history(sport: str, today: date, backfill: bool = False) -> dict:
    """Both manual and daily refreshes publish the same success/failure contract."""
    if sport not in ('nba','nfl','cfb'):
        raise ValueError('Unsupported sport')
    publish_snapshot('refresh:'+sport,dict(status='running',started_at=datetime.now(timezone.utc).isoformat()))
    try:
        coverage=refresh(sport,today,backfill)
        result=dict(status='complete',finished_at=datetime.now(timezone.utc).isoformat(),coverage=coverage)
    except Exception as exc:
        result=dict(status='failed',finished_at=datetime.now(timezone.utc).isoformat(),**error_fields(exc))
    publish_snapshot('refresh:'+sport,result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sport', choices=['nba','nfl','cfb','both'], default='both')
    parser.add_argument('--backfill', action='store_true')
    args = parser.parse_args()
    try:
        failed=False
        for sport in ['nfl','nba'] if args.sport == 'both' else [args.sport]:
            result=refresh_history(sport, date.today(), args.backfill)
            print(json.dumps({'sport':sport,**result}))
            failed=failed or result['status']!='complete'
        if failed:
            raise SystemExit(1)
    except Exception as exc:
        # Provider/DB exception text can contain URLs with credentials.
        raise SystemExit(f'Stat refresh failed ({type(exc).__name__})') from None


if __name__ == '__main__':
    main()
