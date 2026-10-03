"""Private outcome-blind Kalshi transfer of the frozen stat-only NFL model.

Offline only. This is a distinct research protocol; sportsbook paper receipts stay unchanged.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl

from sportsbet.quant import history_shadow, nfl_stat_only_shadow, kalshi_role_shadow as role
from sportsbet.quant import kalshi_role_shadow_v2 as v3
from sportsbet.quant import kalshi_role_shadow_v4 as v4
from sportsbet.quant.history_features import history_estimates
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_market_settlement import verify_cohort
from sportsbet.quant.kalshi_pair_capture import unpack

PROTOCOL = 'kalshi-nfl-stat-only-forward-transfer-v1'
NY = ZoneInfo('America/New_York')


def build(pair: dict, archive: dict, sources: Path, schedule: Path,
          schedule_sha256: str, *, now: datetime,
          strict_prior20_rows: list[dict] | None = None) -> dict:
    """Replay one fresh pregame pair without choosing new coefficients or lines."""
    if now.utcoffset() is None or now < clock(nfl_stat_only_shadow.FROZEN_AT):
        raise ValueError('frozen model time has not arrived')
    cohort, original = unpack(pair)
    verify_cohort(archive, cohort)
    if original['protocol'] not in (v3.VERSION,v4.VERSION):
        raise ValueError('unexpected frozen source protocol')
    if sources.is_symlink() or not sources.is_dir():
        raise ValueError('source directory missing or linked')
    manifest_path=sources/'source-manifest.json'
    if (manifest_path.is_symlink() or not manifest_path.is_file()
            or not 0 < manifest_path.stat().st_size <= 2_000_000):
        raise ValueError('source manifest missing or unbounded')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    source_builder=v3.build_report if original['protocol']==v3.VERSION else v4.build_report
    if source_builder(archive, cohort, sources, manifest,
                      now=clock(original['generated_at'])) != original:
        raise ValueError('original source and model replay changed')
    if (len(schedule_sha256)!=64 or any(c not in '0123456789abcdef' for c in schedule_sha256)
            or schedule.is_symlink() or not schedule.is_file()
            or not 0 < schedule.stat().st_size <= 1_000_000):
        raise ValueError('pinned schedule missing or unbounded')
    schedule_raw = schedule.read_bytes()
    if hashlib.sha256(schedule_raw).hexdigest() != schedule_sha256:
        raise ValueError('pinned schedule changed')
    quoted_targets=archive['evidence']['sources']['kalshi']['targets']
    aliases={quoted_targets[row['team_target_id']]['details']['abbreviation']
             for row in cohort['selections']} & {'JAC','JAX'}
    if aliases=={'JAC','JAX'}:
        raise ValueError('Conflicting Jacksonville quote aliases')
    jacksonville=original['protocol']==v4.VERSION and aliases=={'JAC'}
    def schedule_team(team: str) -> str:
        normalized=role.team(team)
        return 'JAC' if jacksonville and normalized=='JAX' else normalized
    days = {}
    for game in pl.read_parquet(schedule).filter(pl.col('game_type') == 'REG').iter_rows(named=True):
        for team in (schedule_team(game['home_team']), schedule_team(game['away_team'])):
            key = (game['season'], game['week'], team)
            if key in days:
                raise ValueError('duplicate historical team-week schedule')
            days[key] = date.fromisoformat(game['gameday'])
    stats, snaps = v3.load_sources(sources, clock(cohort['captured_at']), manifest)
    if original['protocol']==v4.VERSION:
        stats,snaps=v4._normalize_jacksonville(archive,cohort,stats,snaps)
    by_player, by_pfr, _ = role._index(stats, snaps)
    identity = role.identity_index(Path(role.__file__).with_name('nfl_role_sources.json.gz'),
                                   clock(cohort['captured_at']))
    source = archive['evidence']['sources']['kalshi']
    offers = {row['ticker']: row for row in cohort['selections']}
    targets = source['prop_inventory']['targets']
    teams = source['targets']
    forecasts = []
    reasons = Counter()
    eligible = [f for f in original['forecasts'] if f['prop_type'] in nfl_stat_only_shadow.MARKETS]
    if len(eligible) != len({f['ticker'] for f in eligible}):
        raise ValueError('duplicate exact research contract')
    for original_forecast in eligible:
        ticker = original_forecast['ticker']
        offer = offers[ticker]
        prop = offer['prop_type']
        try:
            match = identity.get(role._name(targets[offer['player_target_id']]['player_name']), set())
            if len(match) != 1:
                raise ValueError('ambiguous_identity')
            gsis, pfr = next(iter(match))
            if gsis != original_forecast['gsis_player_id']:
                raise ValueError('forecast_identity_changed')
            quoted_team = schedule_team(teams[offer['team_target_id']]['details']['abbreviation'])
            start = clock(offer['scheduled_game_start_time'])
            target_day = start.astimezone(NY).date()
            target_season=target_day.year if target_day.month>=9 else target_day.year-1
            if now >= start or not any(day == target_day for (season, week, team), day in days.items()
                                           if season == target_season and team == quoted_team):
                raise ValueError('invalid_future_schedule')
            stat = role.STAT[prop]
            history = role._player_history(gsis, pfr, stat, by_player, by_pfr)[-40:]
            if len(history) < 20:
                raise ValueError('insufficient_history')
            rows = []
            for game in history:
                day = days.get((game['season'], game['week'], game['team']))
                if day is None or day >= target_day or day >= clock(cohort['captured_at']).astimezone(NY).date():
                    raise ValueError('history_schedule_or_chronology')
                rows.append({'day': day, 'team': game['team'], stat: game['value']})
            line = float(offer['line'])
            model = nfl_stat_only_shadow.artifact()['models'][prop]
            if (not math.isfinite(line) or line < model['minimum_offer_line']
                    or not (line * 2).is_integer() or line.is_integer()):
                raise ValueError('unsupported_line')
            estimate = history_estimates(rows, stat, None, target_day, line)
            knots = sorted({.5, line} | {max(.5, math.floor(float(row[stat]))+.5) for row in rows})
            curve = [history_shadow.predicted_over(
                history_estimates(rows, stat, None, target_day, knot)['features'], model, guard=False)
                for knot in knots]
            if any(right > left + 1e-12 for left, right in zip(curve, curve[1:])):
                raise ValueError('nonmonotone_candidate')
            probability = history_shadow.predicted_over(estimate['features'], model)
            history_sha256 = digest([{'day': row['day'].isoformat(),
                'team': row['team'], stat: row[stat]} for row in rows])
            forecasts.append({'ticker': ticker, 'milestone_id': offer['milestone_id'],
                'gsis_player_id': gsis, 'prop_type': prop, 'line': offer['line'],
                'scheduled_game_start_time': offer['scheduled_game_start_time'],
                'model_over_probability': probability,
                'unfitted_prior_probability': estimate['base'],
                'sample_games': len(rows), 'snap_backed_zeros': sum(
                    game['zero_from_offense_snaps'] for game in history),
                'history_sha256': history_sha256})
            if strict_prior20_rows is not None:
                strict_prior20_rows.append({'ticker': ticker,
                    'history_sha256': history_sha256,
                    'prior20_over_probability':
                    (sum(row[stat] > line for row in rows[-20:]) + .5) / 21})
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            allowed = {'ambiguous_identity', 'forecast_identity_changed', 'invalid_future_schedule',
                'insufficient_history', 'history_schedule_or_chronology', 'unsupported_line',
                'nonmonotone_candidate', 'outside_frozen_feature_range', 'stat_without_offense_snap',
                'stat_snap_team_conflict', 'missing_played_stat', 'invalid_played_stat'}
            reason = str(exc)
            reasons[reason if reason in allowed else 'invalid_source_or_feature'] += 1
    if len(forecasts) + sum(reasons.values()) != len(eligible):
        raise AssertionError('fixed denominator changed')
    forecasts.sort(key=lambda row: row['ticker'])
    if strict_prior20_rows is not None:
        strict_prior20_rows.sort(key=lambda row: row['ticker'])
        if [row['ticker'] for row in strict_prior20_rows] != [row['ticker'] for row in forecasts]:
            raise AssertionError('Strict prior-20 forecast identity changed')
    receipt = {'protocol': PROTOCOL, 'generated_at': now.isoformat(),
        'frozen_model_version': nfl_stat_only_shadow.VERSION,
        'frozen_model_artifact_sha256': nfl_stat_only_shadow.ARTIFACT_SHA256,
        'frozen_implementation_sha256': nfl_stat_only_shadow.implementation_sha256(),
        'source_model_protocol': original['protocol'],
        'source_forecasts_sha256': original['forecasts_sha256'],
        'market_selection_sha256': cohort['selection_sha256'],
        'schedule_source_sha256': schedule_sha256,
        'source_manifest_sha256': digest(manifest),
        'eligible_contracts': len(eligible), 'predicted_contracts': len(forecasts),
        'unavailable_reasons': dict(sorted(reasons.items())),
        'forecast_sha256': digest(forecasts), 'forecasts': forecasts,
        'matched_new_market_prices': 0, 'authenticated_settlements': 0,
        'qualified_picks': 0, 'edge_established': False, 'execution_ready': False}
    return receipt


def _input(path: Path, maximum: int) -> dict:
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= maximum):
        raise ValueError('input missing or unbounded')
    value=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value,dict):
        raise ValueError('input is not an object')
    return value


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair',type=Path,required=True)
    parser.add_argument('--market',type=Path,required=True)
    parser.add_argument('--source-dir',type=Path,required=True)
    parser.add_argument('--schedule',type=Path,required=True)
    parser.add_argument('--schedule-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('exclusive research output already exists')
    pair=_input(args.pair,5_000_000)
    archive=_input(args.market,25_000_000)
    receipt=build(pair,archive,args.source_dir,args.schedule,args.schedule_sha256,
                  now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(receipt,stream,indent=2,sort_keys=True,allow_nan=False)
    print(json.dumps({key: receipt[key] for key in ('protocol', 'generated_at',
        'eligible_contracts', 'predicted_contracts', 'unavailable_reasons',
        'forecast_sha256', 'matched_new_market_prices', 'qualified_picks', 'edge_established')},
        sort_keys=True))

if __name__ == '__main__':
    main()
