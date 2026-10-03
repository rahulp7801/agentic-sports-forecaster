"""Pregame strict last-20 history comparator for a new fixed NFL cohort."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_pair_capture import unpack
from sportsbet.quant.kalshi_stat_only_transfer import build as transfer

VERSION = 'kalshi-nfl-stat-only-next-prior20-control-v1'


def build(pair: dict, market: dict, forecast: dict, decisions: dict,
          sources: Path, schedule: Path, schedule_sha256: str,
          *, now: datetime) -> dict:
    rows: list[dict] = []
    reproduced = transfer(pair, market, sources, schedule, schedule_sha256,
                          now=clock(forecast['generated_at']),
                          strict_prior20_rows=rows)
    cohort, _ = unpack(pair)
    first_start = min(clock(row['scheduled_game_start_time'])
                      for row in cohort['selections'])
    decided = clock(decisions['decided_at'])
    if (forecast != reproduced or now.utcoffset() is None
            or not decided <= now < first_start
            or (now-decided) > timedelta(minutes=5)
            or decisions['model_receipt_sha256'] != digest(forecast)
            or decisions['model_forecast_sha256'] != forecast['forecast_sha256']):
        raise ValueError('Strict prior-20 fixed pregame scope changed')
    candidates = sorted(row['ticker'] for row in decisions['candidates'])
    if (len(candidates) != decisions['candidates_count']
            or len(candidates) != len(set(candidates))
            or not set(candidates) <= {row['ticker'] for row in rows}):
        raise ValueError('Strict prior-20 candidate identity changed')
    return {'protocol': VERSION, 'generated_at': now.isoformat(),
            'forecast_receipt_sha256': digest(forecast),
            'decision_receipt_sha256': digest(decisions),
            'source_manifest_sha256': forecast['source_manifest_sha256'],
            'original_forecasts': len(rows), 'fixed_paper_decisions': len(candidates),
            'forecast_rows_sha256': digest(rows), 'forecast_rows': rows,
            'candidate_tickers_sha256': digest(candidates),
            'outcomes_used': False, 'prices_changed': False,
            'consumer_pick_qualified': False, 'edge_established': False}
