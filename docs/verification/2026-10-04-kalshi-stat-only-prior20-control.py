"""Outcome-blind strict prior-20 comparator on the original fixed NFL paper decisions.

No provider call, result read, model fit, decision reselection or publication.
The private output is intentionally excluded from Git.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl

from sportsbet.quant import kalshi_role_shadow as role
from sportsbet.quant import kalshi_role_shadow_v2 as role_v3
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_pair_capture import unpack
from sportsbet.quant.kalshi_stat_only_forward_eval import _pinned, preflight, SCHEDULE_SHA256

NY = ZoneInfo('America/New_York')
SOURCE_DIR = Path('.local/verified-timely-pair-20261003/sources')
SCHEDULE = Path('.local/team-share-sources/games.parquet')


def control(output: Path, *, verify: bool = False) -> dict:
    if verify:
        if output.is_symlink() or not output.is_file() or not 0 < output.stat().st_size <= 100_000:
            raise ValueError('Original control receipt missing or unbounded')
        retained = json.loads(output.read_text(encoding='utf-8'))
        now = clock(retained['generated_at'])
    else:
        now = datetime.now(timezone.utc)
    pair, market, forecast, quotes, decisions = (
        _pinned(Path('.local') / filename, name) for name, filename in (
            ('pair', 'verified-timely-pair-20261003/pair.json'),
            ('market', 'verified-timely-pair-20261003/market-archive.json'),
            ('forecast', 'kalshi-stat-only-probabilities-20261004.json'),
            ('quotes', 'kalshi-stat-only-quotes-20261004.json'),
            ('decisions', 'kalshi-stat-only-ask-decisions-20261004.json')))
    pre, _ = preflight(pair, market, forecast, quotes, decisions, SOURCE_DIR, SCHEDULE)
    first_start = min(clock(row['scheduled_game_start_time']) for row in forecast['forecasts'])
    if now >= first_start:
        raise ValueError('Strict prior-20 pregame control was not captured before first kickoff')
    if (SCHEDULE.is_symlink() or hashlib.sha256(SCHEDULE.read_bytes()).hexdigest()
            != SCHEDULE_SHA256):
        raise ValueError('Pinned schedule changed')

    cohort, original = unpack(pair)
    manifest = original['source_manifest']
    if role_v3.build_report(market, cohort, SOURCE_DIR, manifest,
                            now=clock(original['generated_at'])) != original:
        raise ValueError('Original source-backed forecast changed')
    stats, snaps = role_v3.load_sources(SOURCE_DIR, clock(cohort['captured_at']), manifest)
    by_player, by_pfr, _ = role._index(stats, snaps)
    identity = role.identity_index(
        Path(role.__file__).with_name('nfl_role_sources.json.gz'),
        clock(cohort['captured_at']))
    days = {}
    for game in pl.read_parquet(SCHEDULE).filter(pl.col('game_type') == 'REG').iter_rows(named=True):
        for team in (role.team(game['home_team']), role.team(game['away_team'])):
            key = (game['season'], game['week'], team)
            if key in days:
                raise ValueError('Duplicate historical team week')
            days[key] = date.fromisoformat(game['gameday'])

    offers = {row['ticker']: row for row in cohort['selections']}
    targets = market['evidence']['sources']['kalshi']['prop_inventory']['targets']
    rows = []
    for forecast_row in forecast['forecasts']:
        offer = offers[forecast_row['ticker']]
        matches = identity.get(role._name(targets[offer['player_target_id']]['player_name']), set())
        if len(matches) != 1:
            raise ValueError('Ambiguous fixed player identity')
        gsis, pfr = next(iter(matches))
        if gsis != forecast_row['gsis_player_id']:
            raise ValueError('Fixed player identity changed')
        stat = role.STAT[forecast_row['prop_type']]
        history = role._player_history(gsis, pfr, stat, by_player, by_pfr)[-40:]
        start = clock(forecast_row['scheduled_game_start_time'])
        target_day = start.astimezone(NY).date()
        games = []
        for game in history:
            day = days.get((game['season'], game['week'], game['team']))
            if (day is None or day >= target_day
                    or day >= clock(cohort['captured_at']).astimezone(NY).date()):
                raise ValueError('History source chronology changed')
            games.append({'day': day.isoformat(), 'team': game['team'], stat: game['value']})
        if (len(games) != forecast_row['sample_games']
                or digest(games) != forecast_row['history_sha256']
                or len(games) < 20):
            raise ValueError('Fixed history commitment changed')
        line = float(forecast_row['line'])
        prior40 = (sum(game[stat] > line for game in games) + .5) / (len(games) + 1)
        if abs(prior40 - float(forecast_row['unfitted_prior_probability'])) > 1e-12:
            raise ValueError('Recorded comparator is not the full-history Jeffreys baseline')
        prior20 = (sum(game[stat] > line for game in games[-20:]) + .5) / 21
        rows.append({'ticker': forecast_row['ticker'],
                     'history_sha256': forecast_row['history_sha256'],
                     'prior20_over_probability': prior20})
    rows.sort(key=lambda row: row['ticker'])
    candidates = {row['ticker'] for row in decisions['candidates']}
    if (len(rows) != pre['model_forecasts'] or len(candidates) != 70
            or not candidates <= {row['ticker'] for row in rows}):
        raise ValueError('Fixed forecast or paper-decision denominator changed')
    receipt = {'protocol': 'kalshi-nfl-stat-only-fixed-prior20-control-v1',
               'generated_at': now.isoformat(), 'first_game_start_time': first_start.isoformat(),
               'forecast_receipt_sha256': hashlib.sha256(
                   Path('.local/kalshi-stat-only-probabilities-20261004.json').read_bytes()).hexdigest(),
               'decision_receipt_sha256': hashlib.sha256(
                   Path('.local/kalshi-stat-only-ask-decisions-20261004.json').read_bytes()).hexdigest(),
               'source_manifest_sha256': digest(manifest),
               'original_forecasts': len(rows), 'fixed_paper_decisions': len(candidates),
               'forecast_rows_sha256': digest(rows), 'forecast_rows': rows,
               'candidate_tickers_sha256': digest(sorted(candidates)),
               'outcomes_used': False, 'prices_changed': False, 'consumer_pick_qualified': False,
               'edge_established': False}
    if verify:
        if receipt != retained:
            raise ValueError('Original strict prior-20 control did not replay')
    else:
        if output.exists() or output.is_symlink():
            raise ValueError('Control output already exists')
        output.write_text(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False), encoding='utf-8')
    return {key: receipt[key] for key in ('protocol', 'generated_at', 'original_forecasts',
                                          'fixed_paper_decisions', 'forecast_rows_sha256')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify', action='store_true',
                        help='Replay the exact original receipt without writing or using outcomes')
    args = parser.parse_args()
    print(json.dumps(control(args.output, verify=args.verify), sort_keys=True))
