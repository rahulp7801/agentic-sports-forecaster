"""Private outcome-blind Kalshi transfer of the frozen stat-only NFL model.

Offline only. This is a distinct research protocol; sportsbook paper receipts stay unchanged.
"""
from __future__ import annotations
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
from sportsbet.quant.history_features import history_estimates
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_market_settlement import verify_cohort
from sportsbet.quant.kalshi_pair_capture import unpack

ROOT = Path('.local/verified-timely-pair-20261003')
SCHEDULE = Path('.local/team-share-sources/games.parquet')
SCHEDULE_SHA256 = '4f27270efeba3af862d250a821ff00578da1ce158b76576b72aa283751b22662'
OUTPUT = Path('.local/kalshi-stat-only-probabilities-20261004.json')
PROTOCOL = 'kalshi-nfl-stat-only-forward-transfer-v1'
NY = ZoneInfo('America/New_York')


def main() -> None:
    now = datetime.now(timezone.utc)
    if now < clock(nfl_stat_only_shadow.FROZEN_AT):
        raise ValueError('frozen model time has not arrived')
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise FileExistsError('exclusive research output already exists')
    pair = json.loads((ROOT/'pair.json').read_text(encoding='utf-8'))
    archive = json.loads((ROOT/'market-archive.json').read_text(encoding='utf-8'))
    cohort, original = unpack(pair)
    verify_cohort(archive, cohort)
    if original['protocol'] != v3.VERSION:
        raise ValueError('unexpected frozen source protocol')
    sources = ROOT/'sources'
    manifest = json.loads((sources/'source-manifest.json').read_text(encoding='utf-8'))
    if v3.build_report(archive, cohort, sources, manifest,
                       now=clock(original['generated_at'])) != original:
        raise ValueError('original source and model replay changed')
    schedule_raw = SCHEDULE.read_bytes()
    if hashlib.sha256(schedule_raw).hexdigest() != SCHEDULE_SHA256:
        raise ValueError('pinned schedule changed')
    days = {}
    for game in pl.read_parquet(SCHEDULE).filter(pl.col('game_type') == 'REG').iter_rows(named=True):
        for team in (role.team(game['home_team']), role.team(game['away_team'])):
            key = (game['season'], game['week'], team)
            if key in days:
                raise ValueError('duplicate historical team-week schedule')
            days[key] = date.fromisoformat(game['gameday'])
    stats, snaps = v3.load_sources(sources, clock(cohort['captured_at']), manifest)
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
            quoted_team = role.team(teams[offer['team_target_id']]['details']['abbreviation'])
            start = clock(offer['scheduled_game_start_time'])
            target_day = start.astimezone(NY).date()
            if now >= start or not any(day == target_day for (season, week, team), day in days.items()
                                           if season == target_day.year and team == quoted_team):
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
            forecasts.append({'ticker': ticker, 'milestone_id': offer['milestone_id'],
                'gsis_player_id': gsis, 'prop_type': prop, 'line': offer['line'],
                'scheduled_game_start_time': offer['scheduled_game_start_time'],
                'model_over_probability': probability,
                'unfitted_prior_probability': estimate['base'],
                'sample_games': len(rows), 'snap_backed_zeros': sum(
                    game['zero_from_offense_snaps'] for game in history),
                'history_sha256': digest([{'day': row['day'].isoformat(),
                    'team': row['team'], stat: row[stat]} for row in rows])})
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
    receipt = {'protocol': PROTOCOL, 'generated_at': now.isoformat(),
        'frozen_model_version': nfl_stat_only_shadow.VERSION,
        'frozen_model_artifact_sha256': nfl_stat_only_shadow.ARTIFACT_SHA256,
        'frozen_implementation_sha256': nfl_stat_only_shadow.implementation_sha256(),
        'source_model_protocol': original['protocol'],
        'source_forecasts_sha256': original['forecasts_sha256'],
        'market_selection_sha256': cohort['selection_sha256'],
        'schedule_source_sha256': SCHEDULE_SHA256,
        'source_manifest_sha256': digest(manifest),
        'eligible_contracts': len(eligible), 'predicted_contracts': len(forecasts),
        'unavailable_reasons': dict(sorted(reasons.items())),
        'forecast_sha256': digest(forecasts), 'forecasts': forecasts,
        'matched_new_market_prices': 0, 'authenticated_settlements': 0,
        'qualified_picks': 0, 'edge_established': False, 'execution_ready': False}
    OUTPUT.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False), encoding='utf-8')
    print(json.dumps({key: receipt[key] for key in ('protocol', 'generated_at',
        'eligible_contracts', 'predicted_contracts', 'unavailable_reasons',
        'forecast_sha256', 'matched_new_market_prices', 'qualified_picks', 'edge_established')},
        sort_keys=True))

if __name__ == '__main__':
    main()
