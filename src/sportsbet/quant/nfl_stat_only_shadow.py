"""Forward-only, untraded NFL stat-only transfer on a recorded corrected-role receipt."""
from __future__ import annotations

from datetime import date
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from sportsbet.ledger import utc_timestamp
from sportsbet.quant import history_shadow as old
from sportsbet.quant import nfl_recent_role_shadow as role
from sportsbet.quant.history_features import FEATURES, history_estimates

ARTIFACT_PATH = Path(__file__).with_name('nfl_stat_only_params.json')
ARTIFACT_SHA256 = 'cfcf0c9e57d3027fcc21e9a105bab03752f80c1a0b4684efa2ab7c09bbdfe35f'
MARKETS = {'rec_yds': 'receiving_yards', 'receptions': 'receptions'}
REASONS = frozenset({
    'unsupported_market', 'unsupported_line', 'outside_prospective_quote_window',
    'role_receipt_unavailable', 'invalid_role_input', 'invalid_stat_only_artifact',
    'outside_frozen_feature_range', 'nonmonotone_candidate', 'invalid_candidate_input',
    'invalid_or_late_recording',
})


@lru_cache(maxsize=1)
def artifact() -> dict:
    raw = ARTIFACT_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ARTIFACT_SHA256:
        raise ValueError('invalid_stat_only_artifact')
    value = json.loads(raw)
    if (value.get('model_version') != 'nfl-stat-only-shadow-v1'
            or value.get('role_version') != role.VERSION
            or value.get('baseline_version') != role.BASELINE_VERSION
            or set(value.get('models', {})) != set(MARKETS)
            or any(model.get('feature_names') != list(FEATURES)
                   for model in value['models'].values())):
        raise ValueError('invalid_stat_only_artifact')
    return value


VERSION = 'nfl-stat-only-shadow-v1'
POLICY = 'complete-receiving-stat-only-transfer-v1'
FROZEN_AT = '2026-10-04T00:00:00+00:00'


@lru_cache(maxsize=1)
def implementation_sha256() -> str:
    return old.digest({
        'candidate': hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest(),
        'features': hashlib.sha256(Path(__file__).with_name('history_features.py').read_text(encoding='utf-8-sig').encode()).hexdigest(),
        'role': role.implementation_sha256(),
        'artifact': ARTIFACT_SHA256,
    })


def _replay(payload: dict) -> tuple[float, dict, str]:
    if payload.get('sport') != 'nfl' or payload.get('prop_type') not in MARKETS:
        raise ValueError('unsupported_market')
    now, line = role._offer(payload)
    params = artifact()
    if (params['model_version'] != VERSION or params['policy_version'] != POLICY
            or params['frozen_at'] != FROZEN_AT or now < utc_timestamp(FROZEN_AT)):
        raise ValueError('outside_prospective_quote_window')
    model = params['models'][payload['prop_type']]
    if line < model['minimum_offer_line']:
        raise ValueError('unsupported_line')
    if role.verified_recorded_shadow_probability(payload) is None:
        raise ValueError('role_receipt_unavailable')
    proof = payload['role_history_shadow']
    inputs = role.decoded_inputs(json.dumps(proof['inputs'], sort_keys=True, separators=(',', ':')))
    rows, _ = role.validated_rows(json.dumps(proof['inputs'], sort_keys=True, separators=(',', ':')))
    if len(rows) < 20 or len(rows) > 40 or inputs['cutoff'] != payload['game_date']:
        raise ValueError('invalid_role_input')
    stat = MARKETS[payload['prop_type']]
    history = [dict(row, team={'LAR': 'LA', 'WSH': 'WAS'}.get(row['team'], row['team']),
                    day=date.fromisoformat(row['day']) if isinstance(row['day'], str) else row['day'])
               for row in rows]
    target = date.fromisoformat(payload['game_date'])
    if any(type(row['day']) is not date or row['day'] >= target for row in history):
        raise ValueError('invalid_role_input')
    estimate = history_estimates(history, stat, None, target, line)
    baseline = estimate['base'] if payload['direction'] == 'over' else 1-estimate['base']
    if (payload['model_sample_size'] != estimate['sample']
            or abs(float(payload['model_probability'])-baseline) > 1e-6
            or abs(float(payload['model_mean_stat'])-estimate['mean']) > .005001):
        raise ValueError('invalid_role_input')
    knots = sorted({line, .5} | {max(.5, math.floor(float(row[stat]))+.5) for row in history})
    curve = [old.predicted_over(history_estimates(history, stat, None, target, knot)['features'],
                                model, guard=False) for knot in knots]
    if any(right > left+1e-12 for left, right in zip(curve, curve[1:])):
        raise ValueError('nonmonotone_candidate')
    over = old.predicted_over(estimate['features'], model)
    return (over if payload['direction'] == 'over' else 1-over), estimate, proof['record_sha256']


def shadow_record(payload: dict) -> dict:
    result = dict(model_version=VERSION, policy_version=POLICY, artifact_sha256=ARTIFACT_SHA256,
                  implementation_sha256=implementation_sha256(),
                  generated_at=payload.get('captured_at'), status='unavailable')
    try:
        probability, estimate, role_hash = _replay(payload)
        result.update(status='predicted', probability=probability,
                      sample_size=estimate['sample'], features=list(estimate['features']),
                      role_record_sha256=role_hash, offer_sha256=old.offer_digest(payload),
                      source_basis='verified_recorded_corrected_role_receipt')
        result['record_sha256'] = old.digest(result)
    except (KeyError, TypeError, ValueError, ArithmeticError, OverflowError) as exc:
        reason = str(exc)
        result['reason'] = reason if reason in REASONS else 'invalid_candidate_input'
    return result


def verified_shadow_probability(payload: dict) -> float | None:
    try:
        record = payload['stat_only_shadow']
        if record.get('status') != 'predicted' or record.get('model_version') != VERSION:
            return None
        expected = shadow_record(payload)
        return record['probability'] if old.digest(record) == old.digest(expected) else None
    except (KeyError, TypeError, ValueError, ArithmeticError, OverflowError):
        return None


def verified_recorded_shadow_probability(payload: dict) -> float | None:
    try:
        receipt = utc_timestamp(payload['stat_only_shadow_recorded_at'])
        decision = utc_timestamp(payload['captured_at'])
        if (receipt < decision or receipt >= utc_timestamp(payload['game_start_time'])
                or (receipt-utc_timestamp(payload['quote_time'])).total_seconds() > 300):
            return None
        return verified_shadow_probability(payload)
    except (KeyError, TypeError, ValueError, ArithmeticError, OverflowError):
        return None
