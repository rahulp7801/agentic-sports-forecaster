"""Supplemental exact teammate report-status audit for the fixed NFL paper cohort.

The original acute-set comparison remains unchanged. This offline report
detects same-player Out/Doubtful switches and Questionable status changes.
It cannot change a forecast, candidate, price, or consumer pick.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

from sportsbet.quant import kalshi_stat_only_context_change as original
from sportsbet.quant import kalshi_stat_only_context_refresh as refresh
from sportsbet.quant import kalshi_stat_only_forward_eval as frozen
from sportsbet.quant import kalshi_stat_only_roster_audit as roster
from sportsbet.quant import kalshi_stat_only_teammate_context as context
from sportsbet.quant.kalshi_market_cohort import digest

VERSION = 'kalshi-nfl-stat-only-context-status-detail-v1'


def _skill_reports(rows: list[dict]) -> dict[str, dict[str, tuple[str, str]]]:
    indexed = original._index(rows, roster_rows=False)
    reports: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)
    for (club, gsis), row in indexed.items():
        if row['position'] in context.SKILL:
            reports[club][gsis] = (row['position'],
                                   row['report_status'] or 'listed_no_final_status')
    return reports


def compare(context_rows: list[dict], forecast_rows: list[dict],
            old_injury: list[dict], new_injury: list[dict]) -> dict:
    old, new = _skill_reports(old_injury), _skill_reports(new_injury)
    forecasts = {row['ticker']: row for row in forecast_rows}
    if len(forecasts) != len(forecast_rows):
        raise ValueError('Duplicate frozen forecast ticker')
    all_counts, high_counts = Counter(), Counter()
    affected_clubs = set()
    for row in context_rows:
        forecast = forecasts.get(row['ticker'])
        if forecast is None:
            raise ValueError('Frozen context ticker missing forecast')
        club, subject = row['historical_team'], forecast['gsis_player_id']
        before, after = old.get(club, {}), new.get(club, {})
        names = (set(before) | set(after)) - {subject}
        changes = [(before.get(name), after.get(name)) for name in names
                   if before.get(name) != after.get(name)]
        flags = dict(
            any_skill_teammate_context_changed=bool(changes),
            acute_teammate_status_changed=any(
                (left and left[1] in context.ACUTE or right and right[1] in context.ACUTE)
                and (left[1] if left else None) != (right[1] if right else None)
                for left, right in changes),
            questionable_teammate_status_changed=any(
                (left and left[1] == 'Questionable' or right and right[1] == 'Questionable')
                and (left[1] if left else None) != (right[1] if right else None)
                for left, right in changes),
            skill_teammate_position_changed=any(
                left and right and left[0] != right[0] for left, right in changes))
        if flags['any_skill_teammate_context_changed']:
            affected_clubs.add(club)
        all_counts['candidates'] += 1
        if row['high_probability']:
            high_counts['candidates'] += 1
        for flag, triggered in flags.items():
            all_counts[flag] += int(triggered)
            if row['high_probability']:
                high_counts[flag] += int(triggered)
    if all_counts['candidates'] != 70 or high_counts['candidates'] != 11:
        raise ValueError('Frozen teammate-context candidate denominator changed')
    return {'all_candidates': dict(sorted(all_counts.items())),
            'high_probability_candidates': dict(sorted(high_counts.items())),
            'distinct_affected_clubs': len(affected_clubs),
            'all_teammate_context_changes_zero':
                all_counts['any_skill_teammate_context_changed'] == 0}


def evaluate(pair: dict, market: dict, forecast: dict, quotes: dict,
             decisions: dict, source_dir: Path, schedule: Path,
             baseline_dir: Path, refresh_dir: Path, context_receipt: dict) -> dict:
    base = original.evaluate(pair, market, forecast, quotes, decisions,
                             source_dir, schedule, baseline_dir, refresh_dir,
                             context_receipt)
    later = refresh.verify(refresh_dir, context_receipt)
    old = context._parquet(baseline_dir / 'injuries_2026.parquet',
                           context.INJURY_SHA256,
                           ['season','season_type','week','team','gsis_id','position','report_status'])
    new = context._parquet(refresh_dir / 'injuries_2026.parquet',
                           later['assets']['injuries']['sha256'],
                           ['season','season_type','week','team','gsis_id','position','report_status'])
    details = compare(context_receipt['rows'], forecast['forecasts'], old, new)
    report = {'protocol': VERSION, 'evaluated_at': datetime.now(timezone.utc).isoformat(),
              'original_change_report_sha256': base['record_sha256'],
              'original_context_record_sha256': context.EXPECTED_RECORD_SHA256,
              'refresh_record_sha256': later['record_sha256'],
              'first_kickoff_at': context_receipt['first_kickoff_at'],
              **details, 'edge_established': False, 'qualified_picks': 0,
              'execution_ready': False}
    report['record_sha256'] = digest(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair','market','forecast','quotes','decisions'):
        parser.add_argument('--'+name, type=Path, required=True)
    for name in ('source-dir','schedule','baseline-dir','refresh-dir','context-receipt','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Supplemental context output already exists')
    pair, market, forecast, quotes, decisions = (
        frozen._pinned(getattr(args, name), name) for name in
        ('pair','market','forecast','quotes','decisions'))
    path = args.context_receipt
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 30_000_000:
        parser.error('Original context receipt missing or unbounded')
    report = evaluate(pair, market, forecast, quotes, decisions, args.source_dir,
                      args.schedule, args.baseline_dir, args.refresh_dir,
                      json.loads(path.read_text(encoding='utf-8')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
