"""Pregame commitment and later venue-only scoring for a fresh NFL paper pair.

This is a separate protocol from the hash-pinned October 4 v1 evaluation.
It never collects quotes or promotes a consumer recommendation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_market_settlement import venue_results, verify_cohort
from sportsbet.quant.kalshi_pair_capture import unpack
from sportsbet.quant import kalshi_role_shadow_v2 as role_v3
from sportsbet.quant import kalshi_role_shadow_v4 as role_v4
from sportsbet.quant import kalshi_stat_only_transfer as transfer
from sportsbet.quant import kalshi_stat_only_decision as paper
from sportsbet.quant import kalshi_stat_only_next_control as prior20
from sportsbet.quant.kalshi_stat_only_source_week import verify_files as verify_source_week
from sportsbet.quant.kalshi_stat_only_next_context import verify as verify_context
from sportsbet.quant.kalshi_role_shadow_eval import _forward_bounds
from sportsbet.quant.kalshi_stat_only_forward_eval import _loss, _price_states, score_states

VERSION = 'kalshi-nfl-stat-only-next-score-v1'
COMMIT_VERSION = 'kalshi-nfl-stat-only-next-commit-v1'
SETTLEMENT_VERSION = 'kalshi-nfl-stat-only-next-unsigned-settlement-v1'
LIMITS = {'pair': 5_000_000, 'market': 25_000_000,
          'forecast': 500_000, 'quotes': 2_000_000,
          'decisions': 500_000, 'control': 100_000,
          'schedule': 1_000_000}


def _input(path: Path, limit: int) -> tuple[dict | None, str]:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise ValueError('Missing, linked, or unbounded pinned input')
    raw = path.read_bytes()
    return (json.loads(raw) if path.suffix == '.json' else None,
            hashlib.sha256(raw).hexdigest())


def _recent_gap_hash(inputs: dict, values: dict) -> str | None:
    path = Path(inputs['pair']).parent/'recent-gap.json'
    if not path.exists() and not path.is_symlink():
        return None
    from sportsbet.quant.kalshi_stat_only_next_recent_gap import freeze
    receipt, raw_hash = _input(path, 100_000)
    if receipt != freeze(values['forecast'], values['decisions'], values['control']):
        raise ValueError('Pregame recent-gap receipt changed')
    return raw_hash


def _receiving_hash(inputs: dict, values: dict, source_dir: Path) -> str | None:
    path = Path(inputs['pair']).parent/'source-receiving.json'
    if not path.exists() and not path.is_symlink():
        return None
    from sportsbet.quant.kalshi_stat_only_source_receiving import verify_files
    receipt, raw_hash = _input(path, 100_000)
    checked = clock(receipt['observed_at'])
    if (checked > clock(values['decisions']['decided_at']) or
            receipt != verify_files(source_dir, observed_at=checked)):
        raise ValueError('Pregame receiving-source receipt changed or late')
    return raw_hash


def preflight(pair: dict, market: dict, forecast: dict, quotes: dict,
              decisions: dict, control: dict, source_dir: Path, schedule: Path,
              schedule_sha256: str) -> tuple[dict, dict]:
    cohort, original = unpack(pair)
    verify_cohort(market, cohort)
    if original.get('protocol') not in (role_v3.VERSION, role_v4.VERSION):
        raise ValueError('Unsupported source model version')
    regenerated = transfer.build(pair, market, source_dir, schedule,
                                 schedule_sha256, now=clock(forecast['generated_at']))
    if forecast != regenerated:
        raise ValueError('Pinned model and history replay changed')
    source_week = verify_source_week(
        source_dir, schedule, observed_at=clock(forecast['generated_at']))
    regenerated_paper = paper.freeze(pair, market, forecast, quotes,
                                     now=clock(decisions['decided_at']))
    if decisions != regenerated_paper:
        raise ValueError('Fixed quote decision replay changed')
    regenerated_control = prior20.build(pair, market, forecast, decisions,
                                        source_dir, schedule, schedule_sha256,
                                        now=clock(control['generated_at']))
    if control != regenerated_control:
        raise ValueError('Strict prior-20 pregame control replay changed')
    prices = _price_states(market, forecast, quotes, clock(decisions['decided_at']))
    first_start = min(clock(row['scheduled_game_start_time'])
                      for row in cohort['selections'])
    last_start = max(clock(row['scheduled_game_start_time'])
                     for row in cohort['selections'])
    report = dict(protocol=VERSION, original_market_contracts=len(cohort['selections']),
                  complete_source_week=source_week['week'],
                  receiving_source_contracts=forecast['eligible_contracts'],
                  model_forecasts=forecast['predicted_contracts'],
                  model_unavailable=forecast['unavailable_reasons'],
                  quote_states=decisions['quote_state_counts'],
                  paper_candidates=decisions['candidates_count'],
                  paper_games=decisions['candidate_games'],
                  strict_prior20_forecasts=control['original_forecasts'],
                  forecast_sha256=forecast['forecast_sha256'],
                  candidates_sha256=decisions['candidates_sha256'],
                  first_selected_start_at=first_start.isoformat(),
                  first_eligible_settlement_at=(last_start+timedelta(hours=6)).isoformat(),
                  authenticated_settlements=0, edge_established=False,
                  qualified_picks=0, execution_ready=False)
    return report, prices


def commit(inputs: dict[str, str], source_dir: Path, *, now: datetime) -> dict:
    values, hashes = {}, {}
    for name, path in inputs.items():
        values[name], hashes[name] = _input(Path(path), LIMITS[name])
    manifest_path = source_dir / 'source-manifest.json'
    manifest, hashes['source_manifest'] = _input(manifest_path, 2_000_000)
    if not isinstance(manifest, dict):
        raise ValueError('Invalid source manifest')
    report, _ = preflight(values['pair'], values['market'], values['forecast'],
                          values['quotes'], values['decisions'], values['control'], source_dir,
                          Path(inputs['schedule']), hashes['schedule'])
    decision_time = clock(values['decisions']['decided_at'])
    if (now.utcoffset() is None or not decision_time <= now
            or (now-decision_time).total_seconds() > 300
            or now >= clock(report['first_selected_start_at'])):
        raise ValueError('Pregame commitment is late or clock invalid')
    context_dir = Path(inputs['pair']).parent/'context'
    context_hash = (verify_context(context_dir, before=decision_time)
                    if context_dir.exists() or context_dir.is_symlink() else None)
    result = dict(protocol=COMMIT_VERSION, committed_at=now.isoformat(),
                input_sha256=dict(sorted(hashes.items())),
                model_version=values['forecast']['frozen_model_version'],
                source_protocol=values['forecast']['source_model_protocol'],
                fixed_model_artifact_sha256=values['forecast']['frozen_model_artifact_sha256'],
                first_selected_start_at=report['first_selected_start_at'],
                forecast_sha256=report['forecast_sha256'],
                candidates_sha256=report['candidates_sha256'],
                paper_candidates=report['paper_candidates'],
                paper_games=report['paper_games'])
    if context_hash is not None:
        result['context_receipt_sha256'] = context_hash
    recent_hash = _recent_gap_hash(inputs, values)
    if recent_hash is not None:
        result['recent_gap_sha256'] = recent_hash
    receiving_hash = _receiving_hash(inputs, values, source_dir)
    if receiving_hash is not None:
        result['receiving_source_sha256'] = receiving_hash
    return result


def committed_preflight(inputs: dict[str, str], source_dir: Path,
                        commitment: dict) -> tuple[dict, dict, dict]:
    """Authenticate every pregame byte before a later venue result read."""
    if commitment.get('protocol') != COMMIT_VERSION:
        raise ValueError('Missing pregame commitment')
    # New attempts retain their schedule beside the pair. Prefer that receipt
    # for publishers and result readers even if the shared path is refreshed
    # or removed. Existing commitments without a copy still require the exact
    # original caller-supplied hash; a damaged copy never falls back.
    schedule_copy = Path(inputs['pair']).parent/'schedule.parquet'
    if schedule_copy.exists() or schedule_copy.is_symlink():
        inputs = {**inputs, 'schedule': str(schedule_copy)}
    values, hashes = {}, {}
    for name, path in inputs.items():
        values[name], hashes[name] = _input(Path(path), LIMITS[name])
    manifest, hashes['source_manifest'] = _input(source_dir/'source-manifest.json',
                                                 2_000_000)
    if not isinstance(manifest, dict) or dict(sorted(hashes.items())) != commitment['input_sha256']:
        raise ValueError('Pregame input hash changed')
    pre, prices = preflight(values['pair'], values['market'], values['forecast'],
                            values['quotes'], values['decisions'], values['control'], source_dir,
                            Path(inputs['schedule']), hashes['schedule'])
    if (not clock(values['decisions']['decided_at'])
            <= clock(commitment['committed_at']) < clock(pre['first_selected_start_at'])
            or (clock(commitment['committed_at'])-
                clock(values['decisions']['decided_at'])).total_seconds() > 300
            or commitment['first_selected_start_at'] != pre['first_selected_start_at']
            or commitment['forecast_sha256'] != pre['forecast_sha256']
            or commitment['candidates_sha256'] != pre['candidates_sha256']
            or commitment['paper_candidates'] != pre['paper_candidates']
            or commitment['paper_games'] != pre['paper_games']
            or commitment['model_version'] != values['forecast']['frozen_model_version']
            or commitment['source_protocol'] != values['forecast']['source_model_protocol']
            or commitment['fixed_model_artifact_sha256'] !=
            values['forecast']['frozen_model_artifact_sha256']):
        raise ValueError('Pregame commitment changed')
    context_dir = Path(inputs['pair']).parent/'context'
    context_hash = (verify_context(context_dir, before=clock(values['decisions']['decided_at']))
                    if context_dir.exists() or context_dir.is_symlink() else None)
    if context_hash != commitment.get('context_receipt_sha256'):
        raise ValueError('Pregame context receipt changed')
    if _recent_gap_hash(inputs, values) != commitment.get('recent_gap_sha256'):
        raise ValueError('Pregame recent-gap commitment changed')
    if _receiving_hash(inputs, values, source_dir) != commitment.get('receiving_source_sha256'):
        raise ValueError('Pregame receiving-source commitment changed')
    return values, pre, prices


def strict_prior20_scores(forecast: dict, control: dict, prices: dict,
                          states: dict) -> tuple[dict, bool]:
    strict_rows = {row['ticker']: row for row in control['forecast_rows']}
    paired_strict = []
    strict_brier, strict_log_loss = [], []
    for row in forecast['forecasts']:
        ticker = row['ticker']
        status, outcome = states[ticker]
        if status != 'venue_verified' or prices[ticker][0] != 'two_sided_exact':
            continue
        actual = Decimal(1 if outcome == 'yes' else 0)
        model = _loss(Decimal(str(row['model_over_probability'])), actual)
        baseline = _loss(Decimal(str(strict_rows[ticker]['prior20_over_probability'])), actual)
        strict_brier.append(baseline[0])
        strict_log_loss.append(baseline[1])
        paired_strict.append((row['milestone_id'], row['gsis_player_id'],
                              model[0]-baseline[0], model[1]-baseline[1]))
    # The shared deterministic interval routine accepts only its original
    # comparator names. Rename its keys after calculation; keep its math fixed.
    strict_bounds = ({key.replace('prior20', 'strict_prior20'): value
                      for key, value in _forward_bounds(paired_strict, 'prior20').items()}
                     if paired_strict else {})
    strict_favor = bool(strict_bounds) and all(
        strict_bounds.get(f'model_minus_strict_prior20_{metric}_{cluster}_cluster_95')
        and Decimal(strict_bounds[
            f'model_minus_strict_prior20_{metric}_{cluster}_cluster_95'][1]) < 0
        for metric in ('brier', 'log_loss') for cluster in ('game', 'player'))
    return dict(strict_prior20_paired_results=len(paired_strict),
                paired_strict_prior20_brier=(
                    str(sum(strict_brier)/len(strict_brier)) if strict_brier else None),
                paired_strict_prior20_log_loss=(
                    str(sum(strict_log_loss)/len(strict_log_loss)) if strict_log_loss else None),
                strict_prior20_bounds=strict_bounds), strict_favor


def evaluate(inputs: dict[str, str], source_dir: Path, commitment: dict,
             settlements: dict, *, now: datetime) -> dict:
    values, pre, prices = committed_preflight(inputs, source_dir, commitment)
    if now.utcoffset() is None or now < clock(pre['first_eligible_settlement_at']):
        raise ValueError('Exact result audit is premature')
    record = dict(settlements)
    recorded_hash = record.pop('record_sha256', None)
    if (settlements.get('protocol') != SETTLEMENT_VERSION
            or settlements.get('pregame_commitment_sha256') != digest(commitment)
            or recorded_hash != digest(record)):
        raise ValueError('Full venue result wrapper or commitment changed')
    from sportsbet.quant.kalshi_stat_only_settlement_capture import validate_clock_proof
    validate_clock_proof(settlements['clock_proof'],
                         clock(pre['first_eligible_settlement_at']),
                         clock(settlements['captured_at']))
    cohort, _ = unpack(values['pair'])
    selection, states = venue_results(values['market'], cohort, settlements,
                                      now=now)
    result = score_states(values['forecast'], values['decisions'], prices, states,
                          full_contracts=len(selection),
                          settlement_sha256=settlements['evidence_sha256'])
    result['protocol'] = VERSION
    # The original v1 scorer calls the broad retained-history prior "prior20".
    # Relabel it for this new report without changing its precommitted math.
    for metric in ('brier', 'log_loss'):
        result[f'paired_retained_history_{metric}'] = result.pop(f'paired_prior_{metric}')
        for bucket in result['snap_backed_zero_sensitivity'].values():
            bucket[f'paired_retained_history_{metric}'] = bucket.pop(f'paired_prior_{metric}')
    result['paired_bounds'] = {key.replace('prior20', 'retained_history'): value
                               for key, value in result['paired_bounds'].items()}
    strict_report, strict_favor = strict_prior20_scores(
        values['forecast'], values['control'], prices, states)
    result.update(strict_report)
    result['probability_support'] = result['probability_support'] and strict_favor
    result['full_venue_result_counts'] = dict(sorted(Counter(
        state for state, _ in states.values()).items()))
    if sum(result['full_venue_result_counts'].values()) != pre['original_market_contracts']:
        raise AssertionError('Exact venue result denominator changed')
    result['pregame_commitment_sha256'] = digest(commitment)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in LIMITS:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--commitment', type=Path)
    parser.add_argument('--settlements', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Exclusive paper output already exists')
    inputs = {name: str(getattr(args, name)) for name in LIMITS}
    if args.commitment and args.settlements:
        commitment, _ = _input(args.commitment, 10_000)
        settlements, _ = _input(args.settlements, 30_000_000)
        result = evaluate(inputs, args.source_dir, commitment, settlements,
                          now=datetime.now(timezone.utc))
    elif not args.commitment and not args.settlements:
        result = commit(inputs, args.source_dir, now=datetime.now(timezone.utc))
    else:
        parser.error('Provide both commitment and settlements to score')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
