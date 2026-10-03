"""Forward-only NFL tuned-history transfer on the corrected, complete receiving baseline.

Untraded research. Frozen v1 coefficients are transferred without fitting. Legacy
workload values are not individually source committed, so this candidate cannot
be promoted without independent validation and prospective matched prices.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from sportsbet.quant import history_shadow as old
from sportsbet.quant import nfl_recent_role_shadow as role
from sportsbet.quant.history_features import history_estimates

VERSION = 'nfl-corrected-workload-shadow-v2'
POLICY = 'corrected-receiving-exact-targets-transfer-v1'
FROZEN_AT = '2026-10-03T17:00:00+00:00'
MARKETS = frozenset({'rec_yds', 'receptions'})
ROW_FIELDS = ('player', 'player_id', 'season', 'week', 'team', 'day', 'game',
              'passing_yards', 'rushing_yards', 'receiving_yards', 'receptions',
              'targets', 'source_provider', 'source_sha256',
              'source_record_sha256', 'source_observed_at')
ARTIFACT_SHA256 = old.digest(dict(version=VERSION, policy=POLICY, frozen_at=FROZEN_AT,
    coefficients=old.ARTIFACT_SHA256, corrected_role=role.ARTIFACT_SHA256,
    workload_commitment=False, markets=sorted(MARKETS)))
REASONS = frozenset({'unsupported_market', 'unsupported_baseline', 'unsupported_line',
    'invalid_exact_offer', 'outside_prospective_quote_window', 'role_receipt_unavailable',
    'history_read_failed', 'insufficient_history', 'duplicate_history_game',
    'invalid_history_identity_or_cutoff', 'missing_or_invalid_history',
    'invalid_history_value', 'future_source_observation', 'invalid_history_commitment',
    'low_prior_workload', 'corrected_history_mismatch', 'baseline_history_mismatch',
    'outside_frozen_feature_range', 'nonmonotone_candidate', 'invalid_shadow_input',
    'invalid_or_late_recording', 'shadow_evaluation_failed'})


@lru_cache(maxsize=1)
def implementation_sha256():
    return hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest()


def _rows(raw):
    if not isinstance(raw, list) or not 20 <= len(raw) <= 40:
        raise ValueError('insufficient_history')
    rows = []
    for item in raw:
        if not isinstance(item, dict) or any(k not in item for k in ROW_FIELDS):
            raise ValueError('invalid_shadow_input')
        row = {k: item[k] for k in ROW_FIELDS}
        if type(row['day']) is str:
            row['day'] = date.fromisoformat(row['day'])
        rows.append(row)
    return rows


def _replay(payload, raw):
    from sportsbet.ledger import utc_timestamp
    now, line = role._offer(payload)
    if now < utc_timestamp(FROZEN_AT):
        raise ValueError('outside_prospective_quote_window')
    if payload.get('sport') != 'nfl' or payload.get('prop_type') not in MARKETS:
        raise ValueError('unsupported_market')
    proof = payload.get('role_history_shadow')
    if not isinstance(proof, dict) or role.verified_shadow_probability(payload) is None:
        raise ValueError('role_receipt_unavailable')
    stat, workload, _ = old.MARKETS['nfl'][payload['prop_type']]
    rows, _, _, target, provenance = old._history(_rows(raw), payload, now)
    encoded = json.dumps(proof['inputs'], sort_keys=True, separators=(',', ':'))
    corrected, _ = role.validated_rows(encoded)
    if len(rows) != len(corrected):
        raise ValueError('corrected_history_mismatch')
    def normalized_team(team):
        return {'LAR':'LA','WSH':'WAS'}.get(team,team)
    for row, expected in zip(rows, corrected):
        if (row['season'] != expected['season'] or row['week'] != expected['week']
                or normalized_team(row['team']) != normalized_team(expected['team'])
                or row['day'].isoformat() != expected['day']
                or row[stat] != expected[stat]):
            raise ValueError('corrected_history_mismatch')
    estimate = history_estimates(rows, stat, workload, target, line)
    base = estimate['base'] if payload['direction'] == 'over' else 1-estimate['base']
    if (payload['model_sample_size'] != estimate['sample']
            or abs(float(payload['model_probability'])-base) > 1e-6
            or payload.get('model_mean_stat') is None
            or abs(float(payload['model_mean_stat'])-estimate['mean']) > .005001):
        raise ValueError('baseline_history_mismatch')
    params = old.parameters('nfl', payload['prop_type'])
    knots = sorted({.5} | {max(.5, math.floor(float(r[stat]))+.5) for r in rows})
    curve = [old.predicted_over(history_estimates(rows,stat,workload,target,k)['features'],
                                params,guard=False) for k in knots]
    if any(b > a+1e-12 for a,b in zip(curve,curve[1:])):
        raise ValueError('nonmonotone_candidate')
    over = old.predicted_over(estimate['features'],params)
    return (over if payload['direction']=='over' else 1-over), estimate, provenance, rows


def shadow_record(payload, raw, *, unavailable=None):
    result = dict(model_version=VERSION, policy_version=POLICY,
        artifact_sha256=ARTIFACT_SHA256, implementation_sha256=implementation_sha256(),
        generated_at=payload.get('captured_at'), status='unavailable')
    try:
        if payload.get('sport') != 'nfl' or payload.get('prop_type') not in MARKETS:
            raise ValueError('unsupported_market')
        if unavailable:
            raise ValueError(unavailable)
        probability, estimate, provenance, rows = _replay(payload, raw)
        from sportsbet.ledger import utc_timestamp
        result['generated_at'] = utc_timestamp(payload['captured_at']).isoformat()
        compact = [{k: row[k] for k in ROW_FIELDS} for row in rows]
        inputs = role.encoded_inputs(json.dumps({'rows': compact}, sort_keys=True, separators=(',', ':'),
                                                default=str, allow_nan=False))
        result.update(status='predicted', probability=probability,
            sample_size=estimate['sample'], features=list(estimate['features']),
            inputs=inputs, core_stat_provenance=provenance,
            workload_source_commitment=False,
            role_record_sha256=payload['role_history_shadow']['record_sha256'],
            offer_sha256=old.offer_digest(payload))
        result['record_sha256'] = old.digest(result)
    except (KeyError, TypeError, ValueError, ArithmeticError, OverflowError) as exc:
        result.update(status='unavailable', reason=str(exc) if str(exc) in REASONS
                      else 'invalid_shadow_input')
    return result


def verified_shadow_probability(payload):
    try:
        record = payload['history_shadow']
        if record.get('status') != 'predicted' or record.get('model_version') != VERSION:
            return None
        raw = role.decoded_inputs(json.dumps(record['inputs'],sort_keys=True,separators=(',',':')))
        expected = shadow_record(payload,raw['rows'])
        return record['probability'] if old.digest(expected)==old.digest(record) else None
    except Exception:
        return None


def verified_recorded_shadow_probability(payload):
    from sportsbet.ledger import utc_timestamp
    try:
        receipt = utc_timestamp(payload['history_shadow_recorded_at'])
        role_receipt = utc_timestamp(payload['role_history_shadow_recorded_at'])
        if (not utc_timestamp(payload['captured_at']) <= role_receipt < utc_timestamp(payload['game_start_time'])
                or not utc_timestamp(payload['captured_at']) <= receipt < utc_timestamp(payload['game_start_time'])
                or not 0 <= (receipt-utc_timestamp(payload['quote_time'])).total_seconds() <= 300
                or not 0 <= (role_receipt-utc_timestamp(payload['quote_time'])).total_seconds() <= 300):
            return None
        if role.verified_recorded_shadow_probability(payload) is None:
            return None
        return verified_shadow_probability(payload)
    except (KeyError,TypeError,ValueError,ArithmeticError):
        return None
