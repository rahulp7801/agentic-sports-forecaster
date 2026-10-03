"""Outcome-blind teammate-risk strata for the fixed October 4 NFL stat-only paper cohort.

This exploratory receipt never modifies the frozen model, asks, candidate set or consumer board.
The nflverse injury parquet is an asset-level snapshot: rows lack individual update times.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq

from sportsbet.quant import kalshi_stat_only_forward_eval as frozen
from sportsbet.quant import kalshi_stat_only_high_probability_eval as high
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_role_shadow import team

VERSION = 'kalshi-nfl-stat-only-teammate-context-diagnostic-v1'
INJURY_SHA256 = '0d1ff127705c932b52ad4719f330cc314cfa2ef968d2abe426c5f6bc0f03228f'
STATS_SHA256 = 'e95d60d7d9572a11032dca70a434b104636ee94f899091b810f71057b65a5d58'
INJURY_ASSET_UPDATED_AT = '2026-10-03T12:26:57+00:00'
INJURY_SOURCE_URL = 'https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2026.parquet'
STATS_SOURCE_URL = 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2026.parquet'
EXPECTED_RECORD_SHA256 = '0fce75d466db103ace59f5adf4034c1e5a60e2fad6795d28a57eec51c269b31a'
SKILL = {'QB', 'RB', 'FB', 'WR', 'TE'}
ACUTE = {'Out', 'Doubtful'}


def _parquet(path: Path, sha256: str, columns: list[str]) -> list[dict]:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 2_000_000:
        raise ValueError('Pinned source absent or unbounded')
    if hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
        raise ValueError('Pinned source hash changed')
    return pq.read_table(path, columns=columns).to_pylist()


def stratum(acute_target_share: Decimal | None, acute_present: bool, questionable: bool) -> str:
    """Predeclared noncausal injury exposure bins from prior-week target share."""
    if acute_target_share is None:
        return 'coverage_unavailable'
    if acute_target_share < 0 or acute_target_share > 1:
        raise ValueError('Invalid historical target share')
    if acute_present and acute_target_share == 0:
        return 'acute_teammate_zero_prior_targets'
    if acute_target_share > Decimal('.25'):
        return 'acute_teammate_over_25pct_prior_targets'
    if acute_target_share > Decimal('.10'):
        return 'acute_teammate_10_to_25pct_prior_targets'
    if acute_target_share > 0:
        return 'acute_teammate_up_to_10pct_prior_targets'
    return 'questionable_teammate_only' if questionable else 'no_reported_skill_teammate_risk'


def preflight(pair: dict, market: dict, forecast: dict, quotes: dict,
              decisions: dict, source_dir: Path, schedule: Path,
              injury_path: Path) -> dict:
    primary = high.evaluate(pair, market, forecast, quotes, decisions, source_dir, schedule)
    first_kickoff = min(clock(row['scheduled_game_start_time']) for row in forecast['forecasts'])
    if not clock(INJURY_ASSET_UPDATED_AT) < first_kickoff:
        raise ValueError('Injury archive updated after first kickoff')
    injuries = _parquet(injury_path, INJURY_SHA256,
        ['season', 'season_type', 'week', 'team', 'gsis_id', 'position', 'report_status'])
    stats = _parquet(source_dir / 'stats_player_week_2026.parquet', STATS_SHA256,
        ['season', 'season_type', 'week', 'player_id', 'team', 'position', 'targets'])
    injury_week = [r for r in injuries if r['season'] == 2026 and r['week'] == 4
                   and r['season_type'] == 'REG']
    by_report = {}
    for row in injury_week:
        key = (team(row['team']), row['gsis_id'])
        if not key[0] or not key[1] or key in by_report:
            raise ValueError('Incomplete or duplicate week 4 injury identity')
        by_report[key] = row
    report_teams = {key[0] for key in by_report}
    if len(report_teams) != 32:
        raise ValueError('Week 4 injury archive has incomplete team coverage')
    prior = [r for r in stats if r['season'] == 2026 and r['season_type'] == 'REG'
             and isinstance(r['week'], int) and 1 <= r['week'] <= 3]
    latest = {}
    team_targets = defaultdict(Decimal)
    player_targets = defaultdict(Decimal)
    seen = set()
    for row in prior:
        key = (row['player_id'], row['week'], team(row['team']))
        if not key[0] and not row['targets']:
            continue  # Three anonymous zero-target source rows cannot affect shares.
        if not key[0] or not key[2] or key in seen:
            raise ValueError('Incomplete or duplicate player-week stats identity')
        seen.add(key)
        old = latest.get(row['player_id'])
        if old is None or row['week'] > old['week']:
            latest[row['player_id']] = row
        elif row['week'] == old['week'] and team(row['team']) != team(old['team']):
            raise ValueError('Ambiguous most recent player team')
        targets = Decimal(str(row['targets'] or 0))
        if targets < 0:
            raise ValueError('Negative historical targets')
        team_targets[team(row['team'])] += targets
        player_targets[(team(row['team']), row['player_id'])] += targets
    by_ticker = {r['ticker']: r for r in forecast['forecasts']}
    if len(by_ticker) != len(forecast['forecasts']):
        raise ValueError('Duplicate frozen forecast ticker')
    rows = []
    for decision in decisions['candidates']:
        forecast_row = by_ticker[decision['ticker']]
        subject = forecast_row['gsis_player_id']
        historical = latest.get(subject)
        club = team(historical['team']) if historical else None
        status = by_report.get((club, subject), {}).get('report_status') if club else None
        subject_status = status if status else ('listed_no_final_status' if (club, subject) in by_report else 'not_listed')
        if club is None or club not in report_teams or team_targets[club] <= 0:
            share, acute_present, questionable, acute_qb = None, False, False, False
        else:
            acute_ids = {gsis for (t, gsis), item in by_report.items()
                         if t == club and gsis != subject and item['position'] in SKILL
                         and item['report_status'] in ACUTE}
            questionable = any(t == club and gsis != subject and item['position'] in SKILL
                               and item['report_status'] == 'Questionable'
                               for (t, gsis), item in by_report.items())
            acute_present = bool(acute_ids)
            acute_qb = any(by_report[(club, gsis)]['position'] == 'QB' for gsis in acute_ids)
            share = sum((player_targets[(club, gsis)] for gsis in acute_ids), Decimal(0)) / team_targets[club]
        probability = Decimal(str(decision['model_win_probability']))
        row = dict(ticker=decision['ticker'], milestone_id=decision['milestone_id'],
                   side=decision['side'], model_win_probability=str(probability),
                   displayed_ask=decision['displayed_ask'],
                   high_probability=probability >= high.THRESHOLD,
                   subject_report_status=subject_status,
                   historical_team=club, teammate_context_stratum=stratum(share, acute_present, questionable),
                   acute_qb_teammate=acute_qb)
        rows.append(row)
    if len(rows) != primary['primary_paper_candidates'] or sum(r['high_probability'] for r in rows) != primary['paper_candidates']:
        raise ValueError('Frozen paper or high-probability denominator changed')
    report = dict(protocol=VERSION, original_market_contracts=primary['original_market_contracts'],
        primary_paper_candidates=len(rows), high_probability_candidates=primary['paper_candidates'],
        selected_tickers_sha256=primary['selected_tickers_sha256'],
        first_kickoff_at=first_kickoff.isoformat(),
        first_eligible_settlement_at=primary['first_eligible_settlement_at'],
        injury_source_sha256=INJURY_SHA256, injury_source_url=INJURY_SOURCE_URL,
        injury_asset_updated_at=INJURY_ASSET_UPDATED_AT,
        stats_source_sha256=STATS_SHA256, stats_source_url=STATS_SOURCE_URL,
        injury_report_team_count=len(report_teams), injury_report_player_count=len(injury_week),
        all_candidate_strata=dict(sorted(Counter(r['teammate_context_stratum'] for r in rows).items())),
        high_probability_strata=dict(sorted(Counter(r['teammate_context_stratum'] for r in rows if r['high_probability']).items())),
        rows=rows, edge_established=False, qualified_picks=0, execution_ready=False)
    return report


def freeze(report: dict, decisions: dict, *, now: datetime) -> dict:
    moment = clock(now.isoformat())
    if not clock(decisions['decided_at']) <= moment < clock(report['first_kickoff_at']):
        raise ValueError('Context receipt must be frozen before first kickoff')
    receipt = dict(report, recorded_at=moment.isoformat())
    receipt['record_sha256'] = digest(receipt)
    return receipt


def score(report: dict, receipt: dict, pair: dict, market: dict, forecast: dict,
          quotes: dict, decisions: dict, source_dir: Path, schedule: Path,
          settlements: dict, *, now: datetime) -> dict:
    if (not EXPECTED_RECORD_SHA256 or receipt.get('record_sha256') != EXPECTED_RECORD_SHA256
            or digest({k:v for k,v in receipt.items() if k != 'record_sha256'}) != EXPECTED_RECORD_SHA256
            or {k:v for k,v in receipt.items() if k not in ('record_sha256', 'recorded_at')} != report
            or not clock(decisions['decided_at']) <= clock(receipt['recorded_at']) < clock(report['first_kickoff_at'])):
        raise ValueError('Pre-result context receipt changed or late')
    primary = high.evaluate(pair, market, forecast, quotes, decisions,
                            source_dir, schedule, settlements, now=now)
    cohort, _ = high.unpack(pair)
    _, states = high.venue_results(market, cohort, settlements, now=now)
    groups = defaultdict(list)
    for row in receipt['rows']:
        if row['high_probability']:
            groups[row['teammate_context_stratum']].append(row)
    results = {}
    for name, rows in sorted(groups.items()):
        counts = Counter()
        wins = 0
        paid = Decimal(0)
        brier = Decimal(0)
        games = set()
        for row in rows:
            state, outcome = states[row['ticker']]
            counts[state] += 1
            if state == 'venue_verified':
                games.add(row['milestone_id'])
                win = Decimal(int(outcome == row['side']))
                wins += int(win)
                paid += Decimal(str(row['displayed_ask']))
                brier += (Decimal(row['model_win_probability']) - win) ** 2
        verified = counts['venue_verified']
        results[name] = dict(candidates=len(rows), games=len({r['milestone_id'] for r in rows}),
            result_counts=dict(sorted(counts.items())), verified=verified,
            verified_games=len(games), verified_wins=wins,
            full_group_win_rate=str(Decimal(wins)/len(rows)) if verified == len(rows) else None,
            full_group_brier=str(brier/verified) if verified and verified == len(rows) else None,
            full_group_gross_unit_profit=str(Decimal(wins)-paid) if verified == len(rows) else None)
    if sum(r['verified'] for r in results.values()) != primary['verified_candidates']:
        raise ValueError('Authenticated subset denominator changed')
    return dict(protocol=VERSION, pre_result_record_sha256=EXPECTED_RECORD_SHA256,
        settlement_evidence_sha256=settlements['evidence_sha256'],
        high_probability_candidates=primary['paper_candidates'],
        verified_candidates=primary['verified_candidates'], result_counts=primary['result_counts'],
        strata=results, edge_established=False, qualified_picks=0, execution_ready=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair','market','forecast','quotes','decisions'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--injuries', type=Path, required=True)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--settlements', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Output already exists')
    pair, market, forecast, quotes, decisions = (
        frozen._pinned(getattr(args, name), name) for name in
        ('pair','market','forecast','quotes','decisions'))
    report = preflight(pair, market, forecast, quotes, decisions,
                       args.source_dir, args.schedule, args.injuries)
    if bool(args.receipt) != bool(args.settlements):
        parser.error('Scoring requires both the pre-result receipt and authenticated settlements')
    if args.receipt:
        def bounded(path: Path) -> dict:
            if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 30_000_000:
                raise ValueError('Scoring receipt missing or unbounded')
            result = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(result, dict):
                raise ValueError('Invalid scoring receipt')
            return result
        output = score(report, bounded(args.receipt), pair, market, forecast, quotes,
                       decisions, args.source_dir, args.schedule, bounded(args.settlements),
                       now=datetime.now(timezone.utc))
    else:
        output = freeze(report, decisions, now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(output, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps({k:v for k,v in output.items() if k != 'rows'}, sort_keys=True))


if __name__ == '__main__':
    main()
