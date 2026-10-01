"""NBA player box score ingestion via nba_api.

Uses LeagueDashPlayerStats (one HTTP call per season) to load season-aggregate
totals. nba_api returns pandas DataFrames — no .to_pandas() call needed.
Mandatory time.sleep(1) between seasons per NBA.com rate limit policy.

Pattern: year-by-year loop mirroring pbp.py with gc.collect() after each season.
"""
from __future__ import annotations

import gc
import math
from sportsbet.ingestion.upsert import upsert_rows
import time
import argparse
import sys
from typing import Optional

import pandas as pd
import sqlalchemy as sa
import structlog
from nba_api.stats.endpoints import LeagueDashPlayerStats

from sportsbet.db.connection import get_sync_engine

log = structlog.get_logger(__name__)

# Column whitelist — only columns needed by downstream NBA quant engine (Phase 12).
# Source: 10-RESEARCH.md / plan 10-02 context interfaces.
NBA_COLUMNS: list[str] = [
    "PLAYER_ID",
    "PLAYER_NAME",
    "TEAM_ID",
    "TEAM_ABBREVIATION",
    "GP",
    "MIN",
    "PTS",
    "REB",
    "AST",
    "FG3M",
    "STL",
    "BLK",
]

# Rename map: nba_api column names -> ORM/DB column names (nba_player_stats table).
RENAME_MAP: dict[str, str] = {
    "PLAYER_ID": "player_id",
    "PLAYER_NAME": "player_name",
    "TEAM_ID": "team_id",
    "TEAM_ABBREVIATION": "team_abbreviation",
    "GP": "games_played",
    "MIN": "minutes",
    "PTS": "points",
    "REB": "rebounds",
    "AST": "assists",
    "FG3M": "threes_made",
    "STL": "steals",
    "BLK": "blocks",
}


COUNT_COLUMNS = ("PLAYER_ID", "TEAM_ID", "GP", "PTS", "REB", "AST", "FG3M", "STL", "BLK")
NUMERIC_COLUMNS = (*COUNT_COLUMNS, "MIN")


def validated_totals(source: object) -> pd.DataFrame:
    """Reject incomplete NBA.com season totals before any database write."""
    if not isinstance(source, pd.DataFrame) or source.empty:
        raise ValueError("NBA season totals response is missing or empty")
    missing = sorted(set(NBA_COLUMNS) - set(source.columns))
    if missing:
        raise ValueError(f"NBA season totals are missing columns: {missing}")
    for column, maximum in (("PLAYER_NAME", 100), ("TEAM_ABBREVIATION", 5)):
        values = source[column]
        if (values.isna().any() or values.astype(str).str.strip().eq("").any()
                or values.astype(str).str.len().gt(maximum).any()):
            raise ValueError(f"NBA season totals contain invalid {column}")
    frame = source[NBA_COLUMNS].copy()
    for column in NUMERIC_COLUMNS:
        values = pd.to_numeric(frame[column], errors="coerce")
        if (values.isna().any() or not values.map(math.isfinite).all()
                or values.lt(0).any()
                or (column in COUNT_COLUMNS and values.mod(1).ne(0).any())):
            raise ValueError(f"NBA season totals contain invalid {column}")
        frame[column] = values.astype("int64") if column in COUNT_COLUMNS else values
    if frame["PLAYER_ID"].le(0).any() or frame["PLAYER_ID"].duplicated().any():
        raise ValueError("NBA season totals contain invalid or duplicate player IDs")
    return frame.rename(columns=RENAME_MAP)


def ingest_nba_seasons(
    seasons: list[int],
    engine: Optional[sa.Engine] = None,
) -> None:
    """Load NBA player season-aggregate totals year-by-year into nba_player_stats.

    Args:
        seasons: List of NBA season start years (e.g. [2022, 2023] for 2022-23 and 2023-24).
        engine: SQLAlchemy sync engine. If None, creates from settings.

    Notes:
        - One HTTP call per season via LeagueDashPlayerStats (Totals, Regular Season).
        - time.sleep(1) between calls — mandatory NBA.com rate limit policy.
        - ReadTimeout (or any Exception) causes season skip with warning log; loop continues.
        - gc.collect() called after each season to prevent OOM accumulation.
        - nba_api returns pandas DataFrames directly — no .to_pandas() call needed.
    """
    if engine is None:
        engine = get_sync_engine()

    for season in seasons:
        # Format season int as "YYYY-YY" — e.g. 2022 -> "2022-23", 2009 -> "2009-10"
        season_str = f"{season}-{str(season + 1)[-2:]}"
        log.info("nba_ingestion.season_start", season=season_str)

        try:
            stats = LeagueDashPlayerStats(
                season=season_str,
                season_type_all_star="Regular Season",
                per_mode_detailed="Totals",
                timeout=30,
            )
            # Mandatory rate limit delay — NBA.com enforces per-request throttling.
            time.sleep(1)

            # nba_api returns pandas DataFrame directly — no .to_pandas() needed.
            frames = stats.get_data_frames()
            df = validated_totals(frames[0] if frames else None)

            # Add season year as integer column for partitioning and queries.
            df["season"] = season

            # Chunked append — UniqueConstraint on (player_id, season) handles duplicates.
            # NEVER use if_exists='replace' — drops and recreates the table.
            with engine.begin() as connection:
                df.to_sql(
                    "nba_player_stats",
                    connection,
                    if_exists="append",
                    index=False,
                    chunksize=500,
                    method=upsert_rows(['player_id', 'season']),
                )
            log.info(
                "nba_ingestion.season_complete",
                season=season_str,
                rows=len(df),
            )

            # Explicit free before next season — prevents OOM accumulation.
            del df
            gc.collect()

        except Exception as exc:
            log.warning(
                "nba_ingestion.season_skipped",
                season=season_str,
                error_type=type(exc).__name__,
            )
            gc.collect()
            continue


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest NBA player season-aggregate stats into nba_player_stats table."
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        default=[2022, 2023, 2024],
        help="Season start years to ingest (e.g. 2022 for 2022-23 season). Default: last 3 seasons.",
    )
    args = parser.parse_args()
    ingest_nba_seasons(args.seasons)
    sys.exit(0)
