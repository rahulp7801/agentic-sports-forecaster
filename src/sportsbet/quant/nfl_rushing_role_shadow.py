"""Prospective, untraded NFL rushing-role candidate with complete offensive history.

This shadow never changes the production forecast, risk gate or public pick. A
future frozen evaluation must establish value against both model and market.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re

from sportsbet.ledger import utc_timestamp
from sportsbet.quant import nfl_recent_role_shadow as source
from sportsbet.quant.history_shadow import digest, offer_digest

VERSION = 'nfl-rushing-role-shadow-v1'
POLICY = 'complete-offense-rushing-current-role-prior20-v1'
FROZEN_AT = '2026-10-01T05:00:00+00:00'
PRIOR_STRENGTH = 20
MIN_CURRENT_GAMES = 2
MAX_LATEST_GAP_DAYS = 30
MARKET = 'rush_yds'
ARTIFACT_SHA256 = digest(dict(version=VERSION, policy=POLICY, frozen_at=FROZEN_AT,
    source_artifact=source.ARTIFACT_SHA256, prior=PRIOR_STRENGTH,
    minimum_current_games=MIN_CURRENT_GAMES, maximum_latest_gap_days=MAX_LATEST_GAP_DAYS,
    scope='prospective-untraded-complete-offense-rushing-history'))
REASONS = frozenset({'unsupported_market', 'outside_source_scope', 'history_read_failed',
    'invalid_role_input', 'incomplete_participation_history', 'conflicting_recovery',
    'invalid_current_roster', 'no_current_role_history', 'insufficient_history',
    'baseline_history_mismatch', 'outside_prospective_quote_window', 'unsupported_line',
    'unsupported_baseline', 'invalid_exact_offer', 'stale_current_role',
    'latest_team_mismatch', 'shadow_evaluation_failed'})


@lru_cache(maxsize=1)
def implementation_sha256():
    return digest({'candidate': hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest(),
                   'source': source.implementation_sha256()})


def shadow_record(payload, inputs, *, unavailable=None):
    result = dict(model_version=VERSION, policy_version=POLICY,
        artifact_sha256=ARTIFACT_SHA256, implementation_sha256=implementation_sha256(),
        generated_at=payload.get('captured_at'), status='unavailable')
    try:
        if payload.get('sport') != 'nfl' or payload.get('prop_type') != MARKET:
            raise ValueError('unsupported_market')
        if payload['player_id'] not in source.artifact()[1]:
            raise ValueError('outside_source_scope')
        if unavailable:
            raise ValueError(unavailable)
        now, line = source._offer(payload)
        result['generated_at'] = now.isoformat()
        if now < utc_timestamp(FROZEN_AT):
            raise ValueError('outside_prospective_quote_window')
        if (len(inputs['players']) != 1 or inputs['players'][0]['player_id'] != payload['player_id']
                or any(len(inputs[key]) > source.MAX_ROWS for key in ('stats', 'snaps', 'supplements'))
                or inputs['cutoff'] != payload['game_date']
                or utc_timestamp(inputs['observed_before']) != utc_timestamp(payload['history_observed_before'])
                or not 0 <= (now-utc_timestamp(inputs['observed_at'])).total_seconds() <= 300):
            raise ValueError('invalid_role_input')
        target = date.fromisoformat(payload['game_date'])
        season = target.year if target.month >= 9 else target.year-1
        if inputs['season_floor'] != season-2:
            raise ValueError('invalid_role_input')
        availability = payload.get('availability', {})
        binding = source.artifact()[1][payload['player_id']]
        if (availability.get('status') != 'observed' or availability.get('roster_confirmed') is not True
                or availability.get('player_id') != binding['espn_player_id']
                or not re.fullmatch('[A-Z]{2,3}', availability.get('team', ''))
                or not 0 <= (now-utc_timestamp(availability['captured_at'])).total_seconds() <= 3600
                or not re.fullmatch('[0-9a-f]{64}', availability.get('roster_source_sha256', ''))
                or not re.fullmatch(r'https://site\.api\.espn\.com/apis/site/v2/sports/football/nfl/teams/[1-9][0-9]*/roster',
                                    availability.get('roster_source_url', ''))):
            raise ValueError('invalid_current_roster')
        canonical = json.dumps(inputs, sort_keys=True, separators=(',', ':'), allow_nan=False)
        encoded = source.encoded_inputs(canonical)
        corrected, recovered = source.validated_rows(json.dumps(encoded, sort_keys=True, separators=(',', ':')))
        baseline = sorted((item['stat'] for item in inputs['stats']
                           if item['stat']['season'] >= inputs['season_floor']
                           and item['game_date'] < inputs['cutoff']
                           and item['stat'].get('rushing_yards') is not None),
                          key=lambda row: (row['season'], row['week']))[-40:]
        if (not 20 <= len(baseline) <= 40 or
                any(type(row['rushing_yards']) is not int or abs(row['rushing_yards']) > 10000
                    for row in baseline)):
            raise ValueError('insufficient_history')
        base_over = (sum(row['rushing_yards'] > line for row in baseline)+.5)/(len(baseline)+1)
        base_probability = base_over if payload['direction'] == 'over' else 1-base_over
        if (payload['model_sample_size'] != len(baseline)
                or abs(payload['model_mean_stat']-sum(row['rushing_yards'] for row in baseline)/len(baseline)) > .005001
                or abs(payload['model_probability']-base_probability) > 1e-6):
            raise ValueError('baseline_history_mismatch')
        if any(type(row.get('rushing_yards')) is not int or abs(row['rushing_yards']) > 10000
               for row in corrected):
            raise ValueError('invalid_role_input')
        team = {'LAR': 'LA', 'WSH': 'WAS'}.get(availability['team'], availability['team'])
        latest = corrected[-1]
        if latest['team'] != team:
            raise ValueError('latest_team_mismatch')
        gap = (target-date.fromisoformat(latest['day'])).days
        if not 0 <= gap <= MAX_LATEST_GAP_DAYS:
            raise ValueError('stale_current_role')
        current = [row for row in corrected if row['season'] == season and row['team'] == team]
        older = [row for row in corrected if row not in current]
        if len(current) < MIN_CURRENT_GAMES or not older:
            raise ValueError('no_current_role_history')
        prior = (sum(row['rushing_yards'] > line for row in older)+.5)/(len(older)+1)
        over = (sum(row['rushing_yards'] > line for row in current)+PRIOR_STRENGTH*prior)/(len(current)+PRIOR_STRENGTH)
        p = over if payload['direction'] == 'over' else 1-over
        result.update(status='predicted', probability=p, counts=dict(sample_size=len(corrected),
            current_role_games=len(current), older_games=len(older), latest_game_gap_days=gap,
            current_over_hits=sum(row['rushing_yards'] > line for row in current),
            older_over_probability=prior), recovered_games=recovered, inputs=encoded,
            offer_sha256=offer_digest(payload), availability_sha256=digest(availability))
        result['record_sha256'] = digest(result)
    except (KeyError, TypeError, ValueError, ArithmeticError, OverflowError) as exc:
        result.update(status='unavailable', reason=str(exc) if str(exc) in REASONS else 'invalid_role_input')
    return result


def verified_shadow_probability(payload):
    try:
        record = payload['rushing_role_shadow']
        if record.get('model_version') != VERSION or record.get('status') != 'predicted':
            return None
        inputs = source.decoded_inputs(json.dumps(record['inputs'], sort_keys=True, separators=(',', ':')))
        expected = shadow_record(payload, inputs)
        return record['probability'] if digest(expected) == digest(record) else None
    except Exception:
        return None
