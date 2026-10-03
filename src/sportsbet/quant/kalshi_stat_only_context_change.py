"""Predeclared change audit for the one-time free NFL context refresh.

Keep the original paper candidate denominator. No outcome, betting value, or
probability is recomputed from the later injury/roster snapshot.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from sportsbet.quant import kalshi_stat_only_forward_eval as frozen
from sportsbet.quant import kalshi_stat_only_teammate_context as context
from sportsbet.quant import kalshi_stat_only_roster_audit as roster
from sportsbet.quant import kalshi_stat_only_context_refresh as refresh
from sportsbet.quant.kalshi_market_cohort import digest
from sportsbet.quant.kalshi_role_shadow import team

VERSION = 'kalshi-nfl-stat-only-context-change-audit-v1'


def _index(rows: list[dict], *, roster_rows: bool) -> dict[tuple[str, str], dict]:
    found = {}
    teams = set()
    for row in rows:
        if row['season'] != 2026 or row['week'] != 4:
            continue
        if (roster_rows and row['game_type'] != 'REG'
                or not roster_rows and row['season_type'] != 'REG'):
            continue
        club = team(row['team'])
        if not club:
            raise ValueError('Week-four context team unavailable')
        teams.add(club)
        gsis = row['gsis_id']
        if roster_rows and not gsis:
            continue  # One known anonymous practice-squad row has no join identity.
        if not gsis or (club, gsis) in found:
            raise ValueError('Week-four context identity missing or duplicated')
        found[(club, gsis)] = row
    if len(teams) != 32:
        raise ValueError('Week-four context team coverage incomplete')
    return found


def _subject_report(row: dict | None) -> str:
    if row is None:
        return 'not_listed'
    return row['report_status'] or 'listed_no_final_status'


def _subject_roster(row: dict | None) -> str:
    return ('same_team_active_roster' if row and row['status'] == 'ACT'
            else 'same_team_other_roster_status' if row else 'missing_or_other_team')


def compare(context_rows: list[dict], forecast_rows: list[dict],
            old_injury: list[dict], new_injury: list[dict],
            old_roster: list[dict], new_roster: list[dict]) -> dict:
    old_inj, new_inj = _index(old_injury, roster_rows=False), _index(new_injury, roster_rows=False)
    old_ros, new_ros = _index(old_roster, roster_rows=True), _index(new_roster, roster_rows=True)
    forecasts = {row['ticker']:row for row in forecast_rows}
    if len(forecasts) != len(forecast_rows):
        raise ValueError('Duplicate frozen forecast ticker')
    all_counts, high_counts = Counter(), Counter()
    old_status, new_status, new_roster_status = Counter(), Counter(), Counter()
    old_acute, new_acute = {}, {}
    for items, store in ((old_inj, old_acute), (new_inj, new_acute)):
        for (club, gsis), value in items.items():
            if value['position'] in context.SKILL and value['report_status'] in context.ACUTE:
                store.setdefault(club, set()).add(gsis)
    for row in context_rows:
        forecast = forecasts.get(row['ticker'])
        if forecast is None:
            raise ValueError('Frozen context ticker missing forecast')
        club, subject = row['historical_team'], forecast['gsis_player_id']
        old_s = _subject_report(old_inj.get((club, subject)))
        new_s = _subject_report(new_inj.get((club, subject)))
        old_r = _subject_roster(old_ros.get((club, subject)))
        new_r = _subject_roster(new_ros.get((club, subject)))
        before = old_acute.get(club, set()) - {subject}
        after = new_acute.get(club, set()) - {subject}
        flags = dict(subject_report_changed=old_s != new_s,
                     subject_roster_changed=old_r != new_r,
                     acute_teammate_set_changed=before != after,
                     subject_now_out_or_doubtful=new_s in context.ACUTE,
                     subject_now_not_on_active_roster=new_r != 'same_team_active_roster')
        all_counts['candidates'] += 1
        if row['high_probability']:
            high_counts['candidates'] += 1
        for name, triggered in flags.items():
            all_counts[name] += int(triggered)
            if row['high_probability']:
                high_counts[name] += int(triggered)
        old_status[old_s] += 1
        new_status[new_s] += 1
        new_roster_status[new_r] += 1
    return dict(all_candidates=dict(sorted(all_counts.items())),
                high_probability_candidates=dict(sorted(high_counts.items())),
                original_subject_report_states=dict(sorted(old_status.items())),
                refreshed_subject_report_states=dict(sorted(new_status.items())),
                refreshed_subject_roster_states=dict(sorted(new_roster_status.items())),
                all_changes_zero=(all_counts['subject_report_changed'] == 0
                                  and all_counts['subject_roster_changed'] == 0
                                  and all_counts['acute_teammate_set_changed'] == 0))


def evaluate(pair: dict, market: dict, forecast: dict, quotes: dict, decisions: dict,
             source_dir: Path, schedule: Path, baseline_dir: Path, refresh_dir: Path,
             context_receipt: dict) -> dict:
    original = context.preflight(pair, market, forecast, quotes, decisions,
                                  source_dir, schedule, baseline_dir / 'injuries_2026.parquet')
    if (context_receipt.get('record_sha256') != context.EXPECTED_RECORD_SHA256
            or digest({k:v for k,v in context_receipt.items() if k != 'record_sha256'})
                != context.EXPECTED_RECORD_SHA256
            or {k:v for k,v in context_receipt.items() if k not in ('record_sha256','recorded_at')}
                != original):
        raise ValueError('Frozen context receipt changed')
    later = refresh.verify(refresh_dir, context_receipt)
    old_inj = context._parquet(baseline_dir / 'injuries_2026.parquet', context.INJURY_SHA256,
                              ['season','season_type','week','team','gsis_id','position','report_status'])
    new_inj = context._parquet(refresh_dir / 'injuries_2026.parquet',
                              later['assets']['injuries']['sha256'],
                              ['season','season_type','week','team','gsis_id','position','report_status'])
    old_ros = context._parquet(baseline_dir / 'roster_weekly_2026.parquet', roster.ROSTER_SHA256,
                              ['season','week','game_type','team','gsis_id','status'])
    new_ros = context._parquet(refresh_dir / 'roster_weekly_2026.parquet',
                              later['assets']['weekly_rosters']['sha256'],
                              ['season','week','game_type','team','gsis_id','status'])
    summary = compare(original['rows'], forecast['forecasts'],
                      old_inj, new_inj, old_ros, new_ros)
    if (summary['all_candidates']['candidates'] != original['primary_paper_candidates']
            or summary['high_probability_candidates']['candidates']
                != original['high_probability_candidates']):
        raise ValueError('Frozen context denominator changed')
    result = dict(protocol=VERSION, evaluated_at=datetime.now(timezone.utc).isoformat(),
                  original_context_record_sha256=context.EXPECTED_RECORD_SHA256,
                  refresh_record_sha256=later['record_sha256'],
                  first_kickoff_at=original['first_kickoff_at'],
                  **summary, edge_established=False, qualified_picks=0,
                  execution_ready=False)
    result['record_sha256'] = digest(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair','market','forecast','quotes','decisions'):
        parser.add_argument('--'+name, type=Path, required=True)
    for name in ('source-dir','schedule','baseline-dir','refresh-dir','context-receipt','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Output already exists')
    pair, market, forecast, quotes, decisions = (
        frozen._pinned(getattr(args, name), name) for name in
        ('pair','market','forecast','quotes','decisions'))
    path = args.context_receipt
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 30_000_000:
        parser.error('Original context receipt missing or unbounded')
    report = evaluate(pair,market,forecast,quotes,decisions,args.source_dir,args.schedule,
                      args.baseline_dir,args.refresh_dir,json.loads(path.read_text(encoding='utf-8')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,sort_keys=True,indent=2,allow_nan=False)
    print(json.dumps(report,sort_keys=True))


if __name__ == '__main__':
    main()
