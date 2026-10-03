"""Separate strict prior-20 diagnostic for the fixed October 4 NFL paper cohort.

The original v1 scorer and its mislabeled broader-history keys remain frozen.
This report uses the independently committed pregame prior-20 receipt.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_role_shadow_eval import _forward_bounds
from sportsbet.quant.kalshi_pair_capture import unpack
from sportsbet.quant.kalshi_market_settlement import venue_results
from sportsbet.quant.kalshi_stat_only_forward_eval import _loss, _pinned, preflight, score_states

VERSION = 'kalshi-nfl-stat-only-strict-prior20-score-v1'
CONTROL_SHA256 = '8b052035e6ebc3b4aaa27f00aea5d03e601cfd414e93fcaee9248634082fa3ff'


def pinned_control(path: Path, forecast: dict, decisions: dict) -> dict:
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= 100_000):
        raise ValueError('Original strict prior-20 control missing or unbounded')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CONTROL_SHA256:
        raise ValueError('Strict prior-20 pregame receipt changed')
    receipt = json.loads(raw)
    rows = receipt['forecast_rows']
    tickers = sorted(row['ticker'] for row in forecast['forecasts'])
    candidates = sorted(row['ticker'] for row in decisions['candidates'])
    if (receipt.get('protocol') != 'kalshi-nfl-stat-only-fixed-prior20-control-v1'
            or clock(receipt['generated_at']) >= min(clock(
                row['scheduled_game_start_time']) for row in forecast['forecasts'])
            or receipt.get('original_forecasts') != len(tickers)
            or receipt.get('fixed_paper_decisions') != len(candidates)
            or len(rows) != len(tickers)
            or [row['ticker'] for row in rows] != tickers
            or receipt.get('forecast_rows_sha256') != digest(rows)
            or receipt.get('candidate_tickers_sha256') != digest(candidates)
            or receipt.get('forecast_receipt_sha256') !=
                '649de1f5595c2dcf789050d63d9612375b2d4cae29751943697db62a52368d58'
            or receipt.get('decision_receipt_sha256') !=
                '81646fd99f2f57cb70ec5b60a9889de93d2d86f99017ca3150b71e2c7df4987e'
            or receipt.get('outcomes_used') is not False
            or receipt.get('prices_changed') is not False):
        raise ValueError('Strict prior-20 fixed identity changed')
    for retained, source in zip(rows, sorted(forecast['forecasts'], key=lambda row:row['ticker']), strict=True):
        if (retained['history_sha256'] != source['history_sha256']
                or not 0 < Decimal(str(retained['prior20_over_probability'])) < 1):
            raise ValueError('Strict prior-20 source identity changed')
    return receipt


def score_fixed(forecast: dict, decisions: dict, control: dict, prices: dict,
                states: dict, *, full_contracts: int, settlement_sha256: str) -> dict:
    by_control = {row['ticker']: row for row in control['forecast_rows']}
    if (set(by_control) != {row['ticker'] for row in forecast['forecasts']}
            or len(by_control) != control['original_forecasts']
            or set(by_control) != set(prices)
            or not set(by_control) <= set(states)):
        raise ValueError('Strict prior-20 scorer scope changed')
    original = score_states(forecast, decisions, prices, states,
                            full_contracts=full_contracts,
                            settlement_sha256=settlement_sha256)
    counts = Counter()
    paired = []
    model_scores = []
    prior_scores = []
    for row in forecast['forecasts']:
        ticker = row['ticker']
        state, outcome = states[ticker]
        counts[state] += 1
        price_state, _, _, _ = prices[ticker]
        if state != 'venue_verified' or price_state != 'two_sided_exact':
            continue
        if outcome not in ('yes', 'no'):
            raise ValueError('Verified venue outcome is not binary')
        yes = Decimal(1 if outcome == 'yes' else 0)
        model = _loss(Decimal(str(row['model_over_probability'])), yes)
        prior = _loss(Decimal(str(by_control[ticker]['prior20_over_probability'])), yes)
        model_scores.append(model)
        prior_scores.append(prior)
        paired.append((row['milestone_id'],row['gsis_player_id'],
                       model[0]-prior[0],model[1]-prior[1]))
    n = len(paired)
    model_brier = str(sum(x[0] for x in model_scores)/n) if n else None
    if (n != original['two_sided_paired_results']
            or model_brier != original['paired_model_brier']):
        raise ValueError('Strict prior-20 pair scope differs from frozen evaluator')
    # The frozen interval helper supports the name 'prior20'; relabel only the
    # new report's fields after applying its unchanged game/player resampling.
    bounds = {key.replace('prior20', 'strict_prior20'): value
              for key, value in _forward_bounds(paired, 'prior20').items()} if paired else {}
    return dict(protocol=VERSION, original_frozen_protocol=original['protocol'],
        original_comparator_actual='jeffreys_retained_20_to_40_games',
        strict_control_protocol=control['protocol'],
        strict_control_sha256=CONTROL_SHA256,
        original_market_contracts=full_contracts,
        original_forecasts=len(forecast['forecasts']),
        original_paper_decisions=decisions['candidates_count'],
        forecast_result_counts=dict(sorted(counts.items())),
        same_price_paired_results=n,
        same_price_paired_games=len({game for game,_,_,_ in paired}),
        paired_model_brier=model_brier,
        paired_strict_prior20_brier=str(sum(x[0] for x in prior_scores)/n) if n else None,
        paired_model_log_loss=str(sum(x[1] for x in model_scores)/n) if n else None,
        paired_strict_prior20_log_loss=str(sum(x[1] for x in prior_scores)/n) if n else None,
        paired_bounds=bounds, all_selected_results_verified=(
            original['candidate_result_counts'].get('venue_verified',0)==decisions['candidates_count']),
        full_cohort_win_rate=None, roi=None, clv=None, probability_support=False,
        edge_established=False, qualified_picks=0, execution_ready=False,
        settlement_evidence_sha256=settlement_sha256)


def evaluate(pair: dict, market: dict, forecast: dict, quotes: dict, decisions: dict,
             source_dir: Path, schedule: Path, settlements: dict | Path, control_path: Path,
             *, now: datetime) -> dict:
    pre, prices = preflight(pair, market, forecast, quotes, decisions, source_dir, schedule)
    if now.utcoffset() is None or now < clock(pre['first_eligible_settlement_at']):
        raise ValueError('Strict prior-20 result audit is premature')
    control = pinned_control(control_path, forecast, decisions)
    if isinstance(settlements, Path):
        if (settlements.is_symlink() or not settlements.is_file()
                or not 0 < settlements.stat().st_size <= 30_000_000):
            raise ValueError('Full venue settlement receipt missing or unbounded')
        settlements = json.loads(settlements.read_text(encoding='utf-8'))
    cohort, _ = unpack(pair)
    selected, states = venue_results(market, cohort, settlements, now=now)
    report = score_fixed(forecast, decisions, control, prices, states,
                         full_contracts=len(selected),
                         settlement_sha256=settlements['evidence_sha256'])
    if len(selected) != pre['original_market_contracts']:
        raise ValueError('Full original venue result denominator changed')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair','market','forecast','quotes','decisions'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-dir',type=Path,required=True)
    parser.add_argument('--schedule',type=Path,required=True)
    parser.add_argument('--settlements',type=Path,required=True)
    parser.add_argument('--control',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Output already exists')
    receipts = [_pinned(getattr(args,name),name)
                for name in ('pair','market','forecast','quotes','decisions')]
    report=evaluate(*receipts,args.source_dir,args.schedule,args.settlements,args.control,
                    now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,sort_keys=True,indent=2,allow_nan=False)
    print(json.dumps({key:report[key] for key in (
        'protocol','original_market_contracts','original_forecasts','original_paper_decisions',
        'same_price_paired_results','edge_established','qualified_picks')},sort_keys=True))


if __name__=='__main__':
    main()
