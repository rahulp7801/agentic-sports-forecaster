"""One attempt at a private, free public-data NFL paper cohort.

The exclusive output directory prevents repeat collection. No sportsbook,
credentialed venue action, dashboard publish, order or bet is reachable here.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import httpx

from sportsbet import market_watch
from sportsbet.market_watch import run as watch
from sportsbet.quant.kalshi_market_cohort import clock
from sportsbet.quant.kalshi_pair_sources import stage
from sportsbet.quant.kalshi_pair_capture import capture as pair_capture, save_pair
from sportsbet.quant.kalshi_stat_only_transfer import build as transfer
from sportsbet.quant.kalshi_stat_only_exact_quote import UnsignedReader, capture as quote_capture
from sportsbet.quant.kalshi_stat_only_decision import freeze as paper_freeze
from sportsbet.quant.kalshi_stat_only_next_control import build as prior20_control
from sportsbet.quant.kalshi_stat_only_next_eval import commit
from sportsbet.quant.kalshi_stat_only_next_context import capture as capture_context
from sportsbet.quant.kalshi_stat_only_source_week import verify_files as verify_source_week


def save(value: dict, path: Path) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)


async def capture(root: Path, schedule: Path, *, window_start: datetime,
                  window_end: datetime, now=None) -> dict:
    now = now or (lambda: datetime.now(timezone.utc))
    started = now()
    private_root = (Path.cwd()/'.local').resolve()
    if (started.utcoffset() is None or window_start.utcoffset() is None
            or window_end.utcoffset() is None or not window_start <= started < window_end
            or not root.resolve().is_relative_to(private_root)
            or root.exists() or root.is_symlink()
            or not schedule.is_file() or schedule.is_symlink()
            or not 0 < schedule.stat().st_size <= 1_000_000):
        raise ValueError('One-shot private capture window or input invalid')
    # This exclusive marker is created before any network read. A failed attempt
    # stays failed and cannot silently collect a second price observation.
    root.mkdir(parents=False, exist_ok=False)
    save({'protocol': 'kalshi-stat-only-next-attempt-v1',
          'started_at': started.isoformat(), 'window_start': window_start.isoformat(),
          'window_end': window_end.isoformat()}, root/'attempt.json')
    source_dir = root/'sources'
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        manifest = stage(source_dir, now=now(), client=client)
        context = capture_context(root/'context', now=now(), client=client)
    source_week = verify_source_week(source_dir, schedule, observed_at=now())
    save(source_week, root/'source-week.json')
    # Force every nested watcher read through the unsigned reader too. A
    # future watcher change cannot silently start signing a venue request.
    with patch.object(market_watch, 'KalshiReader', UnsignedReader):
        summary, archive = await watch('nfl', 20, 20, False, provider='kalshi')
    if summary['sources']['kalshi']['status'] != 'observed':
        raise ValueError('Public NFL market coverage unavailable')
    market_path = root/'market.json'
    with market_path.open('xb') as output:
        output.write(Path(archive).read_bytes())
    market = json.loads(market_path.read_text(encoding='utf-8'))
    pair = pair_capture(market, source_dir, started_at=now(),
                        source_manifest=manifest)
    pair_path = root/'pair.json'
    save_pair(pair, pair_path)
    schedule_sha256 = hashlib.sha256(schedule.read_bytes()).hexdigest()
    forecast = transfer(pair, market, source_dir, schedule, schedule_sha256,
                        now=now())
    forecast_path = root/'forecast.json'
    save(forecast, forecast_path)
    async with UnsignedReader() as reader:
        quotes = await quote_capture(forecast, reader, now=now)
    quotes_path = root/'quotes.json'
    save(quotes, quotes_path)
    decisions = paper_freeze(pair, market, forecast, quotes, now=now())
    decisions_path = root/'decisions.json'
    save(decisions, decisions_path)
    control = prior20_control(pair, market, forecast, decisions, source_dir,
                              schedule, schedule_sha256, now=now())
    control_path = root/'control.json'
    save(control, control_path)
    inputs = {'pair': pair_path, 'market': market_path, 'forecast': forecast_path,
              'quotes': quotes_path, 'decisions': decisions_path,
              'control': control_path, 'schedule': schedule}
    commitment = commit(inputs, source_dir, now=now())
    save(commitment, root/'commitment.json')
    return {'selected_contracts': pair['selected_contracts'],
            'context_status': context['status'],
            'complete_source_week': source_week['week'],
            'source_forecasts': pair['forecast_contracts'],
            'stat_only_forecasts': forecast['predicted_contracts'],
            'paper_candidates': decisions['candidates_count'],
            'paper_games': decisions['candidate_games'],
            'commitment_sha256': hashlib.sha256(
                (root/'commitment.json').read_bytes()).hexdigest(),
            'edge_established': False, 'qualified_picks': 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--window-start', required=True)
    parser.add_argument('--window-end', required=True)
    args = parser.parse_args()
    report = asyncio.run(capture(args.output_dir, args.schedule,
                                 window_start=clock(args.window_start),
                                 window_end=clock(args.window_end)))
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
