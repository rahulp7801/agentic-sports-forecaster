"""Refresh 2025-26 NBA season totals without deleting the previous snapshot.

Run from the repository root: python ingest_stats_2025.py
"""
from __future__ import annotations

import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import sys
sys.path.insert(0, "src")

import pandas as pd
from dotenv import load_dotenv
from nba_api.stats.endpoints import LeagueDashPlayerStats

from sportsbet.db.connection import get_sync_engine
from sportsbet.ingestion.nba import NBA_COLUMNS, RENAME_MAP
from sportsbet.ingestion.upsert import upsert_rows

SEASON = 2025
REQUIRED_COLUMNS = ("PLAYER_ID", "PLAYER_NAME")


def ingest_stats_2025(engine=None) -> int:
    """Validate the provider snapshot, then upsert it in one transaction."""
    season_str = f"{SEASON}-{str(SEASON + 1)[-2:]}"
    stats = LeagueDashPlayerStats(
        season=season_str,
        season_type_all_star="Regular Season",
        per_mode_detailed="Totals",
        timeout=60,
    )
    frames = stats.get_data_frames()
    if not frames or not isinstance(frames[0], pd.DataFrame):
        raise ValueError("NBA season totals response is missing")

    source = frames[0]
    missing = set(REQUIRED_COLUMNS) - set(source.columns)
    if missing or source.empty:
        raise ValueError(f"NBA season totals are empty or missing required columns: {sorted(missing)}")
    if source["PLAYER_ID"].isna().any() or source["PLAYER_ID"].duplicated().any():
        raise ValueError("NBA season totals contain missing or duplicate player IDs")
    if source["PLAYER_NAME"].isna().any() or source["PLAYER_NAME"].astype(str).str.strip().eq("").any():
        raise ValueError("NBA season totals contain missing player names")

    frame = source[[column for column in NBA_COLUMNS if column in source.columns]].rename(
        columns=RENAME_MAP
    ).copy()
    frame["season"] = SEASON
    if engine is None:
        engine = get_sync_engine()
    with engine.begin() as connection:
        frame.to_sql(
            "nba_player_stats",
            connection,
            if_exists="append",
            index=False,
            chunksize=500,
            method=upsert_rows(["player_id", "season"]),
        )
    return len(frame)


if __name__ == "__main__":
    load_dotenv()
    count = ingest_stats_2025()
    print(f"Upserted {count} NBA player season rows for {SEASON}")