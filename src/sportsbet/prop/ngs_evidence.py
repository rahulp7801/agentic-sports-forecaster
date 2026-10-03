"""Pregame-only NFL Next Gen Stats context for published forecasts."""
from __future__ import annotations

from datetime import date, datetime
import math
import json
import re

import asyncpg

METRICS = {
    "passing": (
        "avg_time_to_throw", "avg_completed_air_yards", "avg_intended_air_yards",
        "aggressiveness",
    ),
    "receiving": (
        "avg_separation", "avg_cushion", "avg_yac_above_expectation",
    ),
    "rushing": (
        "efficiency", "percent_attempts_gte_eight_defenders",
        "rush_yards_over_expected", "avg_time_to_los",
    ),
}
PROP_STAT_TYPE = {
    "pass_yds": "passing",
    "pass_tds": "passing",
    "rush_yds": "rushing",
    "rec_yds": "receiving",
    "receptions": "receiving",
}
TEAM_ALIASES = {"LAR": "LA", "WSH": "WAS"}
MAX_SAMPLE_WEEKS = 8
EVIDENCE_VERSION = 'ngs-row-commitment-v2'

_EVIDENCE_QUERY = """
    WITH selected AS (
        SELECT DISTINCT ON (season,stat_type) * FROM public.ngs_partition_catalog
        WHERE stat_type=$2 AND season BETWEEN $3-1 AND $3
          AND source_observed_at <= $5 AND recorded_at <= $5
          AND ($6::bigint[] IS NULL OR version_id=ANY($6::bigint[]))
        ORDER BY season,stat_type,recorded_at DESC,version_id DESC
    ), prior AS (
        SELECT n.* FROM public.ngs_history_versions n
        JOIN selected v ON n.partition_version_id=v.version_id
        WHERE player_gsis_id=$1 AND n.stat_type=$2
          AND (n.season < $3 OR (n.season=$3 AND week < $4))
          AND week >= 1 AND n.source_observed_at <= $5
        ORDER BY n.season DESC,week DESC
        LIMIT 8
    )
    SELECT COUNT(*) AS sample_weeks,
           jsonb_agg(to_jsonb(prior) ORDER BY season DESC,week DESC) AS source_rows,
           jsonb_agg(DISTINCT jsonb_build_object('version_id',partition_version_id,
             'season',season,'stat_type',stat_type,'source_sha256',source_sha256,
             'record_set_sha256',record_set_sha256,'recorded_at',partition_available_at,
             'normalization_version',normalization_version,'row_count',partition_rows)) AS partition_refs,
           jsonb_agg(jsonb_build_object('season',season,'week',week,'team',team_abbr)
             ORDER BY season DESC,week DESC) AS sample_periods,
           AVG(avg_time_to_throw) AS avg_time_to_throw,
           AVG(avg_completed_air_yards) AS avg_completed_air_yards,
           AVG(avg_intended_air_yards) AS avg_intended_air_yards,
           AVG(aggressiveness) AS aggressiveness,
           AVG(avg_separation) AS avg_separation,
           AVG(avg_cushion) AS avg_cushion,
           AVG(avg_yac_above_expectation) AS avg_yac_above_expectation,
           AVG(efficiency) AS efficiency,
           AVG(percent_attempts_gte_eight_defenders) AS percent_attempts_gte_eight_defenders,
           AVG(rush_yards_over_expected) AS rush_yards_over_expected,
           AVG(avg_time_to_los) AS avg_time_to_los,
           MAX(source_provider) AS source_provider,
           MAX(source_url) AS source_url,
           MAX(source_sha256) AS source_sha256,
           MAX(source_observed_at) AS source_observed_at,
           COUNT(DISTINCT source_provider) AS source_provider_count,
           COUNT(DISTINCT source_url) AS source_url_count,
           COUNT(DISTINCT source_sha256) AS source_version_count,
           COUNT(*) FILTER (WHERE source_provider IS NULL OR source_url IS NULL
             OR source_sha256 IS NULL OR source_observed_at IS NULL) AS invalid_source_rows
    FROM prior
"""


def verified_tracking_rows(value, count, player_id, stat_type, source_hash,
                           observed_before, aggregate, periods, refs):
    """Replay retained row commitments before publishing descriptive averages."""
    from sportsbet.ingestion.ngs import METRIC_COLUMNS
    from sportsbet.ingestion.provenance import row_sha256
    rows=json.loads(value) if isinstance(value,str) else value
    if not isinstance(rows,list) or len(rows)!=count:
        raise ValueError('Tracking source rows must cover the full sample')
    identities=set()
    source_periods=[]
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError('Invalid tracking source row')
        if (row['player_gsis_id']!=player_id or row['stat_type']!=stat_type
                or row['source_provider']!='nflverse_ngs'
                or row['source_sha256']!=source_hash
                or row['source_url']!=aggregate['source_url']):
            raise ValueError('Tracking source identity differs from sample')
        observed=datetime.fromisoformat(row['source_observed_at'])
        if (observed.utcoffset() is None or observed>aggregate['source_observed_at']
                or (observed_before is not None and observed>observed_before)):
            raise ValueError('Tracking row is outside its observation cutoff')
        ref=next((r for r in refs if r['season']==row['season']),None)
        if (ref is None or row['partition_version_id']!=ref['version_id']
                or row['source_sha256']!=ref['source_sha256']
                or row['record_set_sha256']!=ref['record_set_sha256']
                or row['normalization_version']!=ref['normalization_version']
                or row['partition_rows']!=ref['row_count']
                or datetime.fromisoformat(row['partition_available_at'])!=datetime.fromisoformat(ref['recorded_at'])
                or observed>datetime.fromisoformat(ref['recorded_at'])):
            raise ValueError('Tracking row differs from its retained partition')
        fields=('season','week','player_gsis_id','team_abbr','player_position','stat_type')+METRIC_COLUMNS[stat_type]
        digest=row_sha256({name:row[name] for name in fields})
        if digest!=row['source_record_sha256']:
            raise ValueError('Tracking row commitment does not match retained metrics')
        identity=(row['season'],row['week'])
        if identity in identities:
            raise ValueError('Duplicate tracking source period')
        identities.add(identity)
        source_periods.append({'season':row['season'],'week':row['week'],
                               'team':TEAM_ALIASES.get(row['team_abbr'],row['team_abbr'])})
    if sorted(source_periods,key=lambda p:(p['season'],p['week']),reverse=True)!=periods:
        raise ValueError('Tracking source periods differ from displayed sample')
    for metric in METRICS[stat_type]:
        values=[float(row[metric]) for row in rows if row[metric] is not None]
        reported=aggregate[metric]
        if (not values and reported is not None) or (values and (
                reported is None or not math.isfinite(float(reported))
                or not math.isclose(float(reported),sum(values)/len(values),rel_tol=1e-12,abs_tol=1e-12))):
            raise ValueError('Tracking average differs from committed rows')


def partition_references(value, season, stat_type, cutoff):
    """Validate private exact-version references retained with each forecast."""
    rows=json.loads(value) if isinstance(value,str) else value
    if not isinstance(rows,list) or not 1<=len(rows)<=2:
        raise ValueError('Invalid tracking partition references')
    result=[];seen=set()
    fields={'version_id','season','stat_type','source_sha256','record_set_sha256',
            'recorded_at','normalization_version','row_count'}
    for row in rows:
        if not isinstance(row,dict) or set(row)!=fields:
            raise ValueError('Incomplete tracking partition reference')
        if (type(row['version_id']) is not int or row['version_id']<=0
                or type(row['season']) is not int or not season-1<=row['season']<=season
                or row['season'] in seen or row['stat_type']!=stat_type
                or type(row['row_count']) is not int or not 1<=row['row_count']<=10000
                or row['normalization_version'] not in ('legacy-ngs-row-v1','ngs-db-precision-v2')
                or any(not isinstance(row[k],str) or re.fullmatch('[0-9a-f]{64}',row[k]) is None
                       for k in ('source_sha256','record_set_sha256'))):
            raise ValueError('Contradictory tracking partition reference')
        moment=datetime.fromisoformat(row['recorded_at'])
        if moment.utcoffset() is None or moment>cutoff:
            raise ValueError('Tracking partition exceeds its availability cutoff')
        seen.add(row['season']);result.append(row|{'recorded_at':moment.isoformat()})
    return sorted(result,key=lambda r:r['season'])


def sample_periods(value, count, season, cutoff_week):
    rows=json.loads(value) if isinstance(value,str) else value
    if not isinstance(rows,list) or len(rows)!=count:
        raise ValueError('Tracking sample periods must cover every retained row')
    result=[];seen=set()
    for row in rows:
        year,week,team=row['season'],row['week'],row['team']
        if (type(year) is not int or type(week) is not int or not season-1<=year<=season
                or not 1<=week<=22 or (year==season and week>=cutoff_week)
                or (year,week) in seen
                or (team is not None and (not isinstance(team,str) or re.fullmatch('[A-Z]{2,3}',team) is None))):
            raise ValueError('Invalid tracking sample period')
        seen.add((year,week))
        result.append(dict(season=year,week=week,team=TEAM_ALIASES.get(team,team)))
    return sorted(result,key=lambda r:(r['season'],r['week']),reverse=True)


async def load_ngs_evidence(
    pool: asyncpg.Pool,
    *,
    player_gsis_id: str,
    season: int,
    game_date: date,
    team: str,
    prop_type: str,
    observed_before: datetime | None = None,
    partition_refs: list[dict] | None = None,
) -> dict | None:
    """Return prior weekly tracking context without modifying model probability."""
    if observed_before is not None and (not isinstance(observed_before, datetime)
            or observed_before.utcoffset() is None):
        raise ValueError('Tracking observation cutoff requires an aware timestamp')
    stat_type = PROP_STAT_TYPE.get(prop_type)
    if (
        stat_type is None
        or re.fullmatch(r"00-[0-9]{7}", player_gsis_id) is None
        or not 2016 <= season <= 2100
        or re.fullmatch(r"[A-Z]{2,3}", team) is None
        or type(game_date) is not date
    ):
        return None
    team = TEAM_ALIASES.get(team, team)
    metrics = METRICS[stat_type]
    async with pool.acquire() as conn:
        games = await conn.fetch(
            """SELECT week FROM games
               WHERE season=$1 AND game_date=$2
                 AND (home_team=$3 OR away_team=$3)
               ORDER BY game_id LIMIT 2""",
            season, game_date, team,
        )
        if len(games) != 1:
            return None
        try:
            cutoff_week = games[0]["week"]
        except (KeyError, TypeError):
            return None
        if type(cutoff_week) is not int or not 1 <= cutoff_week <= 22:
            return None
        # Use the database clock for an unbounded live read. The app host and
        # database can differ slightly; exact replay still uses retained IDs.
        selected_before=observed_before or await conn.fetchval('SELECT clock_timestamp()')
        if not isinstance(selected_before,datetime) or selected_before.utcoffset() is None:
            return None
        pinned=partition_references(partition_refs,season,stat_type,selected_before) if partition_refs is not None else None
        row = await conn.fetchrow(
            _EVIDENCE_QUERY, player_gsis_id, stat_type, season, cutoff_week,
            selected_before, [r['version_id'] for r in pinned] if pinned is not None else None,
        )
    if row is None or not row["sample_weeks"]:
        return None
    expected_url = (
        "https://github.com/nflverse/nflverse-data/releases/download/"
        f"nextgen_stats/ngs_{stat_type}.parquet"
    )
    if (
        type(row["sample_weeks"]) is not int or not 1 <= row["sample_weeks"] <= MAX_SAMPLE_WEEKS
        or row.get("invalid_source_rows", 0) != 0
        or row["source_provider_count"] != 1
        or row["source_url_count"] != 1
        or row["source_version_count"] != 1
        or row["source_provider"] != "nflverse_ngs"
        or row["source_url"] != expected_url
        or not isinstance(row["source_sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", row["source_sha256"]) is None
        or not isinstance(row["source_observed_at"], datetime)
        or row["source_observed_at"].utcoffset() is None
        or (observed_before is not None and row["source_observed_at"] > observed_before)
    ):
        return None
    try:
        refs=partition_references(row['partition_refs'],season,stat_type,selected_before)
        if pinned is not None and refs!=pinned:
            return None
        periods=sample_periods(row['sample_periods'],row['sample_weeks'],season,cutoff_week)
        verified_tracking_rows(row.get('source_rows'),row['sample_weeks'],player_gsis_id,
            stat_type,row['source_sha256'],selected_before,row,periods,refs)
    except (KeyError,TypeError,ValueError):
        return None
    values = {
        column: float(row[column])
        for column in metrics
        if row[column] is not None
    }
    if not values or any(not math.isfinite(value) for value in values.values()):
        return None
    return {
        "status": "observed",
        "evidence_version": EVIDENCE_VERSION,
        "stat_type": stat_type,
        "sample_weeks": int(row["sample_weeks"]),
        "cutoff_season": season,
        "cutoff_week": cutoff_week,
        "cutoff_exclusive": True,
        "sample_periods": periods,
        "roster_team": team,
        "metrics": values,
        "source_provider": row["source_provider"],
        "source_url": row["source_url"],
        "source_sha256": row["source_sha256"],
        "source_observed_at": row["source_observed_at"].isoformat(),
        "probability_adjusted": False,
        # Private forecast evidence only. The consumer projection explicitly
        # selects public fields and does not export these version references.
        "partition_refs": refs,
        "version_selected_before": selected_before.isoformat(),
        **({"observed_before": observed_before.isoformat()} if observed_before is not None else {}),
    }
