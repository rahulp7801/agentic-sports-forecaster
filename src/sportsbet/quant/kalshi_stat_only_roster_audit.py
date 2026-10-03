"""Independent pregame roster check for the pinned NFL stat-only context receipt.

An ACT roster code means on the active roster, not game-day participation.
This check cannot revise the frozen predictions or paper candidates.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq

from sportsbet.quant import kalshi_stat_only_forward_eval as frozen
from sportsbet.quant import kalshi_stat_only_teammate_context as context
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_role_shadow import team

VERSION = 'kalshi-nfl-stat-only-week4-roster-audit-v1'
ROSTER_SHA256 = '4792e44d65e6df9b56e39cb4c16d172e08175a2e6a9daf25cfb718b0d0533bbf'
ROSTER_ASSET_UPDATED_AT = '2026-10-03T12:30:28+00:00'
ROSTER_URL = 'https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2026.parquet'


def summarize(roster_rows: list[dict], injury_rows: list[dict],
              context_rows: list[dict], forecast_rows: list[dict]) -> dict:
    current = {}
    unidentified = 0
    for row in roster_rows:
        if row['season'] != 2026 or row['week'] != 4 or row['game_type'] != 'REG':
            continue
        key = (team(row['team']), row['gsis_id'])
        if key[0] and not key[1]:
            unidentified += 1
            continue
        if not key[0] or key in current:
            raise ValueError('Incomplete or duplicate current-week roster identity')
        current[key] = row
    if len({key[0] for key in current}) != 32:
        raise ValueError('Current-week roster has incomplete team coverage')
    by_ticker = {row['ticker']: row for row in forecast_rows}
    if len(by_ticker) != len(forecast_rows):
        raise ValueError('Duplicate forecast ticker')
    counts = Counter()
    high_counts = Counter()
    acute_all = set()
    acute_high = set()
    for row in context_rows:
        forecast = by_ticker.get(row['ticker'])
        if forecast is None:
            raise ValueError('Frozen context ticker has no forecast')
        club = row['historical_team']
        if not club:
            counts['subject_team_unavailable'] += 1
            if row['high_probability']:
                high_counts['subject_team_unavailable'] += 1
            continue
        subject_id = forecast['gsis_player_id']
        for injury in injury_rows:
            if (injury['season'] == 2026 and injury['week'] == 4
                    and team(injury['team']) == club and injury['gsis_id'] != subject_id
                    and injury['position'] in context.SKILL
                    and injury['report_status'] in context.ACUTE):
                key = (club, injury['gsis_id'])
                acute_all.add(key)
                if row['high_probability']:
                    acute_high.add(key)
        subject = current.get((club, subject_id))
        state = ('same_team_active_roster' if subject and subject['status'] == 'ACT'
                 else 'same_team_other_roster_status' if subject else 'missing_or_other_team')
        counts[state] += 1
        if row['high_probability']:
            high_counts[state] += 1
    if sum(counts.values()) != len(context_rows):
        raise ValueError('Roster subject denominator changed')
    def states(keys: set[tuple[str, str]]) -> dict[str, int]:
        found = Counter()
        for key in keys:
            value = current.get(key)
            state = ('same_team_active_roster' if value and value['status'] == 'ACT'
                     else 'same_team_other_roster_status' if value else 'missing_or_other_team')
            found[state] += 1
        return dict(sorted(found.items()))
    return dict(current_week_roster_rows=len(current), unidentified_week4_roster_rows=unidentified,
                roster_team_count=32,
                subject_candidates=len(context_rows), subject_states=dict(sorted(counts.items())),
                high_probability_candidates=sum(bool(r['high_probability']) for r in context_rows),
                high_probability_subject_states=dict(sorted(high_counts.items())),
                acute_reported_skill_teammates=len(acute_all),
                acute_teammate_roster_states=states(acute_all),
                high_probability_acute_teammates=len(acute_high),
                high_probability_acute_teammate_roster_states=states(acute_high))


def audit(pair: dict, market: dict, forecast: dict, quotes: dict, decisions: dict,
          source_dir: Path, schedule: Path, injury_path: Path, roster_path: Path,
          context_receipt: dict, *, now: datetime) -> dict:
    report = context.preflight(pair, market, forecast, quotes, decisions,
                               source_dir, schedule, injury_path)
    if (context_receipt.get('record_sha256') != context.EXPECTED_RECORD_SHA256
            or digest({k:v for k,v in context_receipt.items() if k != 'record_sha256'}) != context.EXPECTED_RECORD_SHA256
            or {k:v for k,v in context_receipt.items() if k not in ('record_sha256','recorded_at')} != report
            or not clock(decisions['decided_at']) <= clock(context_receipt['recorded_at'])
            < clock(report['first_kickoff_at'])):
        raise ValueError('Frozen context receipt changed or late')
    now = clock(now.isoformat())
    if not clock(ROSTER_ASSET_UPDATED_AT) <= now < clock(report['first_kickoff_at']):
        raise ValueError('Roster audit requires pregame source and observation')
    roster = context._parquet(roster_path, ROSTER_SHA256,
                             ['season','week','game_type','team','gsis_id','status'])
    injuries = context._parquet(injury_path, context.INJURY_SHA256,
                               ['season','week','team','gsis_id','position','report_status'])
    summary = summarize(roster, injuries, report['rows'], forecast['forecasts'])
    result = dict(protocol=VERSION, recorded_at=now.isoformat(),
                  first_kickoff_at=report['first_kickoff_at'],
                  context_record_sha256=context.EXPECTED_RECORD_SHA256,
                  injury_source_sha256=context.INJURY_SHA256,
                  roster_source_sha256=ROSTER_SHA256,
                  roster_source_url=ROSTER_URL,
                  roster_asset_updated_at=ROSTER_ASSET_UPDATED_AT,
                  **summary, edge_established=False, qualified_picks=0,
                  execution_ready=False)
    result['record_sha256'] = digest(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair','market','forecast','quotes','decisions'):
        parser.add_argument('--'+name, type=Path, required=True)
    for name in ('source-dir','schedule','injuries','roster','context-receipt','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Output already exists')
    pair, market, forecast, quotes, decisions = (
        frozen._pinned(getattr(args, name), name) for name in
        ('pair','market','forecast','quotes','decisions'))
    path = args.context_receipt
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 30_000_000:
        parser.error('Frozen context receipt missing or unbounded')
    receipt = json.loads(path.read_text(encoding='utf-8'))
    result = audit(pair, market, forecast, quotes, decisions, args.source_dir,
                   args.schedule, args.injuries, args.roster, receipt,
                   now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
