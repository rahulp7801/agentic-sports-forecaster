"""Versioned repair of the missing retained-history log-loss report field.

The original pregame inputs, scorer, clock proof and strict-prior math are reused.
This adds a missing aggregate; it does not fit, select, collect or promote picks.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from sportsbet.quant import kalshi_stat_only_next_eval as frozen
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_market_settlement import venue_results
from sportsbet.quant.kalshi_pair_capture import unpack
from sportsbet.quant.kalshi_stat_only_forward_eval import _loss, score_states
from sportsbet.quant.kalshi_stat_only_settlement_capture import validate_clock_proof

VERSION = 'kalshi-nfl-stat-only-next-score-v2'
LIMITS = frozen.LIMITS
COMMIT_VERSION = frozen.COMMIT_VERSION
SETTLEMENT_VERSION = frozen.SETTLEMENT_VERSION
committed_preflight = frozen.committed_preflight
_input = frozen._input
REPAIR_FILES = ('kalshi_stat_only_next_eval_v2.py',
    'kalshi_stat_only_next_series_v3.py',
    'kalshi_stat_only_next_recent_gap_eval_v3.py',
    'kalshi_role_weighting_eval_v3.py',
    'kalshi_stat_only_next_teammate_study_v3.py')


def evaluation_hash() -> str:
    from sportsbet.quant.kalshi_stat_only_next_teammate_study_v2 import implementation
    hashes = implementation()
    root = Path(__file__).resolve().parent
    for name in REPAIR_FILES:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Report repair implementation missing or linked')
        hashes[name] = hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    return digest(hashes)


def retained_history_log_loss(forecast: dict, prices: dict, states: dict,
                              expected_pairs: int) -> str | None:
    losses = []
    for row in forecast['forecasts']:
        ticker = row['ticker']
        status, outcome = states[ticker]
        if status != 'venue_verified' or prices[ticker][0] != 'two_sided_exact':
            continue
        if outcome not in ('yes', 'no'):
            raise ValueError('Verified binary result invalid')
        actual = Decimal(1 if outcome == 'yes' else 0)
        losses.append(_loss(Decimal(str(row['unfitted_prior_probability'])), actual)[1])
    if len(losses) != expected_pairs:
        raise ValueError('Retained-history paired denominator changed')
    return str(sum(losses)/len(losses)) if losses else None


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
    validate_clock_proof(settlements['clock_proof'],
                         clock(pre['first_eligible_settlement_at']),
                         clock(settlements['captured_at']))
    cohort, _ = unpack(values['pair'])
    selection, states = venue_results(values['market'], cohort, settlements, now=now)
    result = score_states(values['forecast'], values['decisions'], prices, states,
                          full_contracts=len(selection),
                          settlement_sha256=settlements['evidence_sha256'])
    result['paired_prior_log_loss'] = retained_history_log_loss(
        values['forecast'], prices, states, result['two_sided_paired_results'])
    for metric in ('brier', 'log_loss'):
        result[f'paired_retained_history_{metric}'] = result.pop(f'paired_prior_{metric}')
        for bucket in result['snap_backed_zero_sensitivity'].values():
            bucket[f'paired_retained_history_{metric}'] = bucket.pop(f'paired_prior_{metric}')
    result['paired_bounds'] = {key.replace('prior20', 'retained_history'): value
                               for key, value in result['paired_bounds'].items()}
    strict_report, strict_favor = frozen.strict_prior20_scores(
        values['forecast'], values['control'], prices, states)
    result.update(strict_report)
    result['probability_support'] = result['probability_support'] and strict_favor
    result['full_venue_result_counts'] = dict(sorted(Counter(
        state for state, _ in states.values()).items()))
    if sum(result['full_venue_result_counts'].values()) != pre['original_market_contracts']:
        raise AssertionError('Exact venue result denominator changed')
    result.update(protocol=VERSION, frozen_score_protocol=frozen.VERSION,
                  evaluation_implementation_sha256=evaluation_hash(),
                  pregame_commitment_sha256=digest(commitment))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in LIMITS:
        parser.add_argument('--'+name, type=Path, required=True)
    for name in ('source-dir', 'commitment', 'settlements', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Exclusive repaired report already exists')
    inputs = {name: str(getattr(args, name)) for name in LIMITS}
    commitment, _ = _input(args.commitment, 10_000)
    # Run the frozen preflight and result gate before reading outcome bytes.
    _, pre, _ = committed_preflight(inputs, args.source_dir, commitment)
    now = datetime.now(timezone.utc)
    if now < clock(pre['first_eligible_settlement_at']):
        parser.error('Before full-cohort result gate; settlement input not read')
    settlements, _ = _input(args.settlements, 30_000_000)
    report = evaluate(inputs, args.source_dir, commitment, settlements, now=now)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps({key: report[key] for key in (
        'protocol', 'two_sided_paired_results', 'probability_support',
        'edge_established', 'qualified_picks')}, sort_keys=True))


if __name__ == '__main__':
    main()
