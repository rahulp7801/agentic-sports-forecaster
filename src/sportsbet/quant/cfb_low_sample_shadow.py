"""Untraded current-team recency candidate for CFB offers with 4–19 prior games.

This is a prospective research hypothesis, not a public pick or demonstrated edge.
The production history model and its 20-game qualification floor are unchanged.
"""
from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
import hashlib
import math
from pathlib import Path
import re

from sportsbet.ingestion.provenance import stat_row_sha256
from sportsbet.model_contract import CFB_HISTORY_POLICY, CFB_MODEL_VERSION
from sportsbet.prop.query_builder import PROP_COLUMN_MAP
from sportsbet.quant import cfb_team_role_shadow as source

VERSION = 'cfb-low-sample-team-recency-shadow-v1'
POLICY = 'cfb-current-team-last-five-prior-eight-v1'
FROZEN_AT = '2026-10-02T08:00:00+00:00'
MIN_HISTORY = 4
MAX_HISTORY = 19
RECENT_GAMES = 5
PRIOR_STRENGTH = 8
MARKETS = source.MARKETS
REASONS = frozenset({'unsupported_offer', 'invalid_quote', 'invalid_roster',
    'history_read_failed', 'invalid_history', 'insufficient_history',
    'no_current_team_history', 'baseline_history_mismatch', 'invalid_shadow_input'})


@lru_cache(maxsize=1)
def implementation_sha256() -> str:
    own = Path(__file__).read_text(encoding='utf-8-sig').replace('\r\n', '\n').encode()
    return source.digest({'low_sample': hashlib.sha256(own).hexdigest(),
                          'source_loader': source.implementation_sha256()})


def shadow_record(payload: dict, rows: list[dict], *, unavailable: str | None = None) -> dict:
    """Bind the estimate to a verified quote, roster, as-of rows, and baseline."""
    from sportsbet.ledger import quote_evidence_valid, settlement_identity_valid, utc_timestamp

    result = dict(model_version=VERSION, policy_version=POLICY,
                  implementation_sha256=implementation_sha256(),
                  generated_at=payload.get('captured_at'), status='unavailable')
    try:
        if unavailable:
            raise ValueError(unavailable)
        if (payload.get('sport') != 'cfb' or payload.get('prop_type') not in MARKETS
                or payload.get('model_version') != CFB_MODEL_VERSION
                or payload.get('history_policy_version') != CFB_HISTORY_POLICY
                or payload.get('direction') not in ('over', 'under')):
            raise ValueError('unsupported_offer')
        now = utc_timestamp(payload['captured_at'])
        cutoff = date.fromisoformat(payload['game_date'])
        observed_before = utc_timestamp(payload['history_observed_before'])
        start = utc_timestamp(payload['game_start_time'])
        quote = utc_timestamp(payload['quote_time'])
        if (now < utc_timestamp(FROZEN_AT)
                or payload.get('forecast_cutoff') != payload['game_date']
                or utc_timestamp(payload['model_generated_at']) != now
                or not observed_before <= now < start
                or not 0 <= (now-quote).total_seconds() <= 300
                or not quote_evidence_valid(payload)
                or not settlement_identity_valid(payload)):
            raise ValueError('invalid_quote')
        availability = payload.get('availability')
        if (not isinstance(availability, dict)
                or availability.get('status') != 'observed'
                or availability.get('roster_confirmed') is not True
                or availability.get('player_id') != payload['player_id']
                or not isinstance(availability.get('team'), str)
                or not re.fullmatch(r'[A-Za-z0-9]{1,10}', availability['team'])
                or not re.fullmatch(r'[0-9a-f]{64}', availability.get('roster_source_sha256', ''))
                or not re.fullmatch(
                    r'https://site\.api\.espn\.com/apis/site/v2/sports/football/college-football/teams/[1-9][0-9]*/roster(?:\?limit=1000)?',
                    availability.get('roster_source_url', ''))
                or not 0 <= (now-utc_timestamp(availability['captured_at'])).total_seconds() <= 3600):
            raise ValueError('invalid_roster')
        line = float(payload['line'])
        if (not math.isfinite(line) or line < .5 or line % 1 != .5
                or payload.get('push_probability') != 0):
            raise ValueError('unsupported_offer')
        if not isinstance(rows, list) or not MIN_HISTORY <= len(rows) <= MAX_HISTORY:
            raise ValueError('insufficient_history')
        season = cutoff.year if cutoff.month >= 8 else cutoff.year-1
        column = PROP_COLUMN_MAP[payload['prop_type']]
        if len({row.get('game_id') for row in rows if isinstance(row, dict)}) != len(rows):
            raise ValueError('invalid_history')
        if any((earlier['game_date'], earlier['game_id']) >=
               (later['game_date'], later['game_id'])
               for earlier, later in zip(rows, rows[1:])):
            raise ValueError('invalid_history')
        for row in rows:
            provider_policy = {
                'sportsdataverse_espn': 'primary-v1',
                'sportsdataverse_espn_supplement': 'cfb-explicit-receiving-v1',
            }
            if (set(row) != set((*source.ROW_FIELDS, *source.SOURCE_FIELDS))
                    or str(row['athlete_id']) != payload['player_id']
                    or not season-2 <= row['season'] <= season
                    or not date.fromisoformat(row['game_date']) < cutoff
                    or type(row[column]) is not int or abs(row[column]) > 10000
                    or row['history_policy_version'] != provider_policy.get(row['source_provider'])
                    or not re.fullmatch(r'[0-9a-f]{64}', row['source_sha256'])
                    or not re.fullmatch(r'[0-9a-f]{64}', row['source_record_sha256'])
                    or utc_timestamp(row['source_observed_at']) > observed_before
                    or stat_row_sha256('cfb', row) != row['source_record_sha256']):
                raise ValueError('invalid_history')
        values = [row[column] for row in rows]
        pooled_over = (sum(value > line for value in values) + .5) / (len(rows)+1)
        baseline = pooled_over if payload['direction'] == 'over' else 1-pooled_over
        if (payload['model_sample_size'] != len(rows)
                or abs(float(payload['model_probability'])-baseline) > 1e-6
                or payload.get('model_mean_stat') is None
                or abs(float(payload['model_mean_stat'])-sum(values)/len(rows)) > .005001):
            raise ValueError('baseline_history_mismatch')
        if rows[-1]['team_abbreviation'] != availability['team']:
            raise ValueError('no_current_team_history')
        boundary = len(rows)-1
        while boundary > 0 and rows[boundary-1]['team_abbreviation'] == availability['team']:
            boundary -= 1
        current = rows[boundary:]
        if len(current) < 2:
            raise ValueError('no_current_team_history')
        recent = current[-RECENT_GAMES:]
        recent_over = (sum(row[column] > line for row in recent) + .5) / (len(recent)+1)
        adjusted_over = (PRIOR_STRENGTH*pooled_over + len(recent)*recent_over) / (
            PRIOR_STRENGTH+len(recent))
        result.update(status='predicted',
            probability=adjusted_over if payload['direction'] == 'over' else 1-adjusted_over,
            pooled_probability=baseline, current_team=availability['team'],
            current_team_games=len(current), other_team_games=boundary,
            recent_team_games=len(recent), prior_strength=PRIOR_STRENGTH,
            sample_size=len(rows), offer_sha256=source.offer_digest(payload),
            availability_sha256=source.digest(availability), inputs=source._pack(rows))
        result['record_sha256'] = source.digest(result)
    except (KeyError, TypeError, ValueError, ArithmeticError, OverflowError) as exc:
        result.update(status='unavailable',
            reason=str(exc) if str(exc) in REASONS else 'invalid_shadow_input')
    return result


def verified_shadow_probability(payload: dict) -> float | None:
    try:
        record = payload['cfb_low_sample_shadow']
        if record.get('model_version') != VERSION or record.get('status') != 'predicted':
            return None
        expected = shadow_record(payload, source._unpack(record['inputs']))
        return record['probability'] if source.digest(expected) == source.digest(record) else None
    except Exception:
        return None


def verified_recorded_shadow_probability(
    raw_payload: str, recorded_at: str | datetime, payload_sha256: str,
) -> float | None:
    """Recompute only from an immutable database-owned prediction receipt."""
    from sportsbet.ledger import utc_timestamp
    import json
    try:
        if (not isinstance(raw_payload, str)
                or hashlib.sha256(raw_payload.encode()).hexdigest() != payload_sha256):
            return None
        payload = json.loads(raw_payload)
        receipt = utc_timestamp(recorded_at)
        if (not utc_timestamp(payload['captured_at']) <= receipt
                < utc_timestamp(payload['game_start_time'])
                or not 0 <= (receipt-utc_timestamp(payload['quote_time'])).total_seconds() <= 300):
            return None
        return verified_shadow_probability(payload)
    except Exception:
        return None
