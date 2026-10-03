"""Post-result exploratory price comparison of the original frozen context bins.

This new diagnostic was defined AFTER results. It never revises the original
pregame receipt, frozen scorer, selections, model, prices or consumer policy.
All bins and both fixed scopes are retained; no collection or orders occur.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

from sportsbet.quant import kalshi_stat_only_teammate_context as context
from sportsbet.quant import kalshi_stat_only_forward_eval as frozen
from sportsbet.quant import kalshi_stat_only_prelock_paper_result as paper
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_market_settlement import venue_results
from sportsbet.quant.kalshi_pair_capture import unpack
from sportsbet.quant.kalshi_stat_only_prior20_eval import pinned_control
from sportsbet.quant.kalshi_role_shadow_eval import _forward_bounds
from sportsbet.quant.kalshi_stat_only_prelock_fee_score import _receipt

VERSION = 'kalshi-nfl-stat-only-context-price-exploratory-v1'
STRATA = ('acute_teammate_zero_prior_targets', 'acute_teammate_up_to_10pct_prior_targets',
          'acute_teammate_10_to_25pct_prior_targets', 'acute_teammate_over_25pct_prior_targets',
          'questionable_teammate_only', 'no_reported_skill_teammate_risk', 'coverage_unavailable')


def _probability(value) -> Decimal:
    try:
        p = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError('Invalid fixed probability') from error
    if not p.is_finite() or not 0 < p < 1:
        raise ValueError('Invalid fixed probability')
    return p


def summarize(rows: list[dict], forecasts: list[dict], prior_rows: list[dict],
              prices: dict, states: dict) -> dict:
    """Only called after complete source/receipt/result replay by evaluate()."""
    by_forecast = {row['ticker']: row for row in forecasts}
    by_prior = {row['ticker']: row for row in prior_rows}
    if (len(by_forecast) != len(forecasts) or len(by_prior) != len(prior_rows)
            or len({row['ticker'] for row in rows}) != len(rows)):
        raise ValueError('Duplicate fixed identity')
    for row in rows:
        ticker, side = row['ticker'], row['side']
        if (side not in ('yes', 'no') or row['teammate_context_stratum'] not in STRATA
                or type(row['high_probability']) is not bool
                or ticker not in by_forecast or ticker not in by_prior
                or ticker not in prices or ticker not in states
                or row['milestone_id'] != by_forecast[ticker]['milestone_id']
                or not by_forecast[ticker]['gsis_player_id']):
            raise ValueError('Missing or changed fixed context identity')
        model = _probability(row['model_win_probability'])
        over = _probability(by_forecast[ticker]['model_over_probability'])
        if model != (over if side == 'yes' else 1-over) or row['high_probability'] != (model >= context.high.THRESHOLD):
            raise ValueError('Fixed side, probability or subset membership changed')
        state, outcome = states[ticker]
        if (state == 'venue_verified' and outcome not in ('yes', 'no')) or (state != 'venue_verified' and outcome is not None):
            raise ValueError('Unverified or nonbinary result carries an outcome')
        _probability(by_prior[ticker]['prior20_over_probability'])
    scopes = {}
    for name, fixed in (('all_original_70', rows), ('original_high_probability_11', [r for r in rows if r['high_probability']])):
        groups = {}
        for label in STRATA:
            selected = [r for r in fixed if r['teammate_context_stratum'] == label]
            result_counts, price_counts = Counter(), Counter()
            wins = 0
            losses = {name: [] for name in ('model', 'market', 'strict_prior20')}
            probabilities = {name: [] for name in losses}
            paired_market, paired_prior, paired_wins = [], [], []
            for row in selected:
                ticker, side = row['ticker'], row['side']
                state, outcome = states[ticker]
                price_state, market_over, _, _ = prices[ticker]
                result_counts[state] += 1
                price_counts[price_state] += 1
                if state != 'venue_verified':
                    continue
                win = Decimal(int(outcome == side))
                wins += int(win)
                if price_state != 'two_sided_exact':
                    continue
                model = _probability(row['model_win_probability'])
                market_over = _probability(market_over)
                prior_over = _probability(by_prior[ticker]['prior20_over_probability'])
                values = {'model': model, 'market': market_over if side == 'yes' else 1-market_over,
                          'strict_prior20': prior_over if side == 'yes' else 1-prior_over}
                scores = {key: frozen._loss(value, win) for key, value in values.items()}
                for key in losses:
                    losses[key].append(scores[key])
                    probabilities[key].append(values[key])
                game, player = row['milestone_id'], by_forecast[ticker]['gsis_player_id']
                paired_market.append((game, player, *(a-b for a,b in zip(scores['model'],scores['market'],strict=True))))
                paired_prior.append((game, player, *(a-b for a,b in zip(scores['model'],scores['strict_prior20'],strict=True))))
                paired_wins.append(win)
            count, binary, paired = len(selected), result_counts['venue_verified'], len(paired_market)
            games = len({row[0] for row in paired_market})
            players = len({row[1] for row in paired_market})
            interval_ready = games >= 2 and players >= 2
            complete = bool(count) and binary == count
            groups[label] = {'fixed_candidates': count, 'fixed_games': len({r['milestone_id'] for r in selected}),
                'fixed_tickers_sha256': digest(sorted(r['ticker'] for r in selected)),
                'result_counts': dict(sorted(result_counts.items())), 'price_counts': dict(sorted(price_counts.items())),
                'verified_binary_candidates': binary, 'verified_binary_wins': wins,
                'verified_subset_win_rate': str(Decimal(wins)/binary) if binary else None,
                'complete_results': complete, 'full_group_win_rate': str(Decimal(wins)/count) if complete else None,
                'same_price_paired_candidates': paired, 'same_price_paired_games': games, 'same_price_paired_players': players,
                'complete_result_and_price_coverage': complete and paired == count,
                'paired_event_win_rate': str(sum(paired_wins)/paired) if paired else None,
                'paired_mean_probability': {key: str(sum(values)/paired) if paired else None for key,values in probabilities.items()},
                'paired_scores': {key: {metric: str(sum(row[index] for row in values)/paired) if paired else None
                    for index,metric in enumerate(('brier','log_loss'))} for key,values in losses.items()},
                'model_minus_market_bounds': _forward_bounds(paired_market, 'market') if interval_ready else None,
                'model_minus_strict_prior20_bounds': _forward_bounds(paired_prior, 'prior20') if interval_ready else None}
        if sum(group['fixed_candidates'] for group in groups.values()) != len(fixed):
            raise ValueError('Context strata lost a fixed candidate')
        scopes[name] = {'fixed_candidates': len(fixed), 'fixed_games': len({r['milestone_id'] for r in fixed}), 'strata': groups}
    return scopes


def evaluate(pair, market, forecast, quotes, decisions, source_dir: Path, schedule: Path,
             injuries: Path, receipt: dict, settlements: dict, control_path: Path, *, now: datetime) -> dict:
    pre, prices = frozen.preflight(pair, market, forecast, quotes, decisions, source_dir, schedule)
    if now.utcoffset() is None or now < clock(pre['first_eligible_settlement_at']):
        raise ValueError('Before full-cohort result gate')
    paper.verify_capture_wrapper(settlements, pre)
    original = context.preflight(pair, market, forecast, quotes, decisions, source_dir, schedule, injuries)
    original_score = context.score(original, receipt, pair, market, forecast, quotes, decisions,
                                   source_dir, schedule, settlements, now=now)
    control = pinned_control(control_path, forecast, decisions)
    cohort, _ = unpack(pair)
    selection, states = venue_results(market, cohort, settlements, now=now)
    if len(selection) != pre['original_market_contracts'] or len(states) != len(selection):
        raise ValueError('Full original venue result denominator changed')
    rows = receipt['rows']
    if len(rows) != 70 or sum(row['high_probability'] for row in rows) != 11:
        raise ValueError('Original context cohort or subset changed')
    scopes = summarize(rows, forecast['forecasts'], control['forecast_rows'], prices, states)
    # The original predeclared score remains authoritative and untouched.
    high = scopes['original_high_probability_11']['strata']
    for label, score in original_score['strata'].items():
        if (high[label]['fixed_candidates'] != score['candidates']
                or high[label]['verified_binary_candidates'] != score['verified']
                or high[label]['verified_binary_wins'] != score['verified_wins']):
            raise ValueError('Original frozen context score disagrees')
    return {'protocol': VERSION, 'generated_at': now.isoformat(), 'analysis_defined_after_results': True,
            'pre_result_context_record_sha256': context.EXPECTED_RECORD_SHA256,
            'original_context_score_sha256': digest(original_score),
            'settlement_evidence_sha256': settlements['evidence_sha256'],
            'strict_prior20_receipt_sha256': hashlib.sha256(control_path.read_bytes()).hexdigest(),
            'scopes': scopes, 'causal_context_effect_established': False, 'prospective_replication': False,
            'edge_established': False, 'qualified_picks': 0, 'fills_verified': False, 'roi': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair','market','forecast','quotes','decisions','source-dir','schedule','injuries','receipt','settlements','control','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Output must be exclusive')
    pair, market, forecast, quotes, decisions = (frozen._pinned(getattr(args,name), name)
        for name in ('pair','market','forecast','quotes','decisions'))
    pre, _ = frozen.preflight(pair,market,forecast,quotes,decisions,args.source_dir,args.schedule)
    now = datetime.now(timezone.utc)
    if now < clock(pre['first_eligible_settlement_at']):
        parser.error('Before full-cohort result gate; settlement input not read')
    report = evaluate(pair,market,forecast,quotes,decisions,args.source_dir,args.schedule,args.injuries,
                      _receipt(args.receipt),_receipt(args.settlements),args.control,now=now)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,indent=2,sort_keys=True,allow_nan=False)
    print(json.dumps({key:report[key] for key in ('protocol','analysis_defined_after_results','edge_established','qualified_picks')},sort_keys=True))


if __name__ == '__main__':
    main()
