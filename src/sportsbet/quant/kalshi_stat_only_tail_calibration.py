"""Pre-result, outcome-blind calibration stress test for the frozen Oct 4 NO cohort.

Only historical 2025 selection bins set the correction. This separate paper
report cannot change the primary model, candidate set, consumer picks or bets.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from sportsbet.quant import kalshi_stat_only_forward_eval as frozen
from sportsbet.quant import kalshi_stat_only_high_probability_eval as high
from sportsbet.quant.kalshi_market_cohort import clock, digest

VERSION = 'kalshi-nfl-stat-only-lower-tail-calibration-diagnostic-v1'
HISTORY_SHA256 = 'c44edb356c163113140863d22d0a1b62440be8bff11df6edae0e39ca7eb69557'
EXPECTED_RECORD_SHA256 = '17ef2bba84abe5b6536063c4da09e6d7c0e7d72afad4234c2cbc6fbb37d59abb'
SELECTED = {'rec_yds': 'logistic_l2_0.01', 'receptions': 'logistic_l2_0.1'}
BANDS = ((Decimal('.1'), Decimal('.2')), (Decimal('.2'), Decimal('.3')))


def pinned_history(path: Path) -> dict:
    if (path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 500_000):
        raise ValueError('Historical calibration report missing or unbounded')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != HISTORY_SHA256:
        raise ValueError('Historical calibration commitment changed')
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get('status') != 'exploratory_unpriced_stat_only':
        raise ValueError('Invalid historical calibration report')
    return value


def offsets(history: dict) -> dict[str, dict[str, Decimal]]:
    result = {}
    for prop, selected in SELECTED.items():
        evaluation = history['props'][prop]['evaluation']
        if evaluation['selected'] != selected:
            raise ValueError('Historical model selection changed')
        bins = evaluation['selection_scores'][selected]['calibration_bins']
        result[prop] = {}
        for low, high_bound in BANDS:
            matched = [row for row in bins if Decimal(str(row['lower'])) == low
                       and Decimal(str(row['upper'])) == high_bound]
            if len(matched) != 1 or type(matched[0]['count']) is not int or matched[0]['count'] < 100:
                raise ValueError('Historical lower-tail bin unavailable')
            row = matched[0]
            predicted, observed = (Decimal(str(row[key])) for key in ('predicted', 'observed'))
            correction = observed - predicted
            if not (Decimal(0) < predicted < Decimal(1)
                    and Decimal(0) < observed < Decimal(1)
                    and Decimal(0) < correction < Decimal('.1')):
                raise ValueError('Invalid historical lower-tail correction')
            result[prop][f'{low}-{high_bound}'] = correction
    return result


def preflight(pair: dict, market: dict, forecast: dict, quotes: dict,
              decisions: dict, source_dir: Path, schedule: Path,
              history: dict) -> tuple[dict, list[tuple[dict, Decimal, Decimal]]]:
    primary = high.evaluate(pair, market, forecast, quotes, decisions, source_dir, schedule)
    correction = offsets(history)
    rows = forecast['forecasts']
    by_ticker = {row['ticker']: row for row in rows}
    if len(by_ticker) != len(rows):
        raise ValueError('Duplicate frozen forecast ticker')
    selected = []
    for decision in decisions['candidates']:
        original = Decimal(str(decision['model_win_probability']))
        if original < high.THRESHOLD:
            continue
        forecast_row = by_ticker[decision['ticker']]
        over = Decimal(str(forecast_row['model_over_probability']))
        prop = forecast_row['prop_type']
        if (decision['side'] != 'no' or prop not in SELECTED
                or abs(original - (1 - over)) > Decimal('0.000000000001')):
            raise ValueError('Frozen high-probability NO identity changed')
        band = next((f'{low}-{high_bound}' for low, high_bound in BANDS
                     if low <= over < high_bound), None)
        if band is None:
            raise ValueError('NO probability outside predeclared historical bins')
        adjusted = original - correction[prop][band]
        if not Decimal(0) < adjusted < Decimal(1):
            raise ValueError('Invalid calibrated probability')
        selected.append((decision, original, adjusted))
    if (len(selected) != primary['paper_candidates']
            or digest(sorted(item[0]['ticker'] for item in selected)) != primary['selected_tickers_sha256']):
        raise ValueError('Frozen diagnostic selection changed')
    count = len(selected)
    first_kickoff = min(clock(row['scheduled_game_start_time']) for row in rows)
    report = dict(protocol=VERSION, primary_protocol=primary['primary_protocol'],
        historical_selection_report_sha256=HISTORY_SHA256,
        correction_by_prop_and_over_band={prop:{band:str(value) for band, value in bands.items()}
                                      for prop, bands in correction.items()},
        original_market_contracts=primary['original_market_contracts'],
        primary_paper_candidates=primary['primary_paper_candidates'],
        paper_candidates=count, paper_games=primary['paper_games'],
        selected_tickers_sha256=primary['selected_tickers_sha256'],
        first_kickoff_at=first_kickoff.isoformat(),
        first_eligible_settlement_at=primary['first_eligible_settlement_at'],
        original_mean_model_win_probability=str(sum(item[1] for item in selected)/count),
        corrected_mean_model_win_probability=str(sum(item[2] for item in selected)/count),
        corrected_at_least_75_count=sum(item[2] >= high.THRESHOLD for item in selected),
        corrected_below_75_count=sum(item[2] < high.THRESHOLD for item in selected),
        result_counts=None, verified_candidates=0, verified_games=0,
        verified_subset_original_brier=None, verified_subset_corrected_brier=None,
        full_group_original_brier=None, full_group_corrected_brier=None,
        verified_subset_original_log_loss=None, verified_subset_corrected_log_loss=None,
        full_group_original_log_loss=None, full_group_corrected_log_loss=None,
        edge_established=False, qualified_picks=0, execution_ready=False)
    return report, selected


def freeze(report: dict, decisions: dict, *, now: datetime) -> dict:
    now = clock(now.isoformat())
    if not clock(decisions['decided_at']) <= now < clock(report['first_kickoff_at']):
        raise ValueError('Calibration receipt must be frozen before first kickoff')
    receipt = dict(report, recorded_at=now.isoformat())
    receipt['record_sha256'] = digest(receipt)
    return receipt


def score(pair: dict, market: dict, forecast: dict, quotes: dict, decisions: dict,
          source_dir: Path, schedule: Path, history: dict, receipt: dict,
          settlements: dict, *, now: datetime) -> dict:
    report, selected = preflight(pair, market, forecast, quotes, decisions,
                                 source_dir, schedule, history)
    if (not isinstance(receipt, dict)
            or receipt.get('record_sha256') != EXPECTED_RECORD_SHA256
            or receipt.get('record_sha256') != digest({k:v for k,v in receipt.items()
                                                     if k != 'record_sha256'})
            or {k:v for k,v in receipt.items() if k not in ('record_sha256','recorded_at')} != report
            or not clock(decisions['decided_at']) <= clock(receipt['recorded_at'])
                < clock(report['first_kickoff_at'])):
        raise ValueError('Pre-result calibration receipt changed or late')
    primary = high.evaluate(pair, market, forecast, quotes, decisions,
                            source_dir, schedule, settlements, now=now)
    cohort, _ = high.unpack(pair)
    _, states = high.venue_results(market, cohort, settlements, now=now)
    original_scores, corrected_scores = [], []
    verified_games, wins = set(), 0
    counts = Counter()
    for decision, original, corrected in selected:
        state, outcome = states[decision['ticker']]
        counts[state] += 1
        if state != 'venue_verified':
            continue
        win = Decimal(int(outcome == decision['side']))
        wins += int(win)
        verified_games.add(decision['milestone_id'])
        original_scores.append(frozen._loss(original, win))
        corrected_scores.append(frozen._loss(corrected, win))
    verified = len(original_scores)
    if (verified != primary['verified_candidates'] or wins != primary['verified_wins']
            or len(verified_games) != primary['verified_games']
            or dict(sorted(counts.items())) != primary['result_counts']):
        raise ValueError('Authenticated high-probability result mismatch')
    report.update(pre_result_record_sha256=receipt['record_sha256'],
        pre_result_recorded_at=receipt['recorded_at'],
        result_counts=primary['result_counts'], verified_candidates=verified,
        verified_games=len(verified_games), settlement_evidence_sha256=primary['settlement_evidence_sha256'])
    for index, metric in enumerate(('brier','log_loss')):
        for label, rows in (('original', original_scores), ('corrected', corrected_scores)):
            value = str(sum(row[index] for row in rows)/verified) if verified else None
            report[f'verified_subset_{label}_{metric}'] = value
            report[f'full_group_{label}_{metric}'] = value if verified == len(selected) else None
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair','market','forecast','quotes','decisions'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--history-report', type=Path, required=True)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--settlements', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Output already exists')
    pair, market, forecast, quotes, decisions = (
        frozen._pinned(getattr(args,name),name) for name in
        ('pair','market','forecast','quotes','decisions'))
    history = pinned_history(args.history_report)
    if bool(args.receipt) != bool(args.settlements):
        parser.error('Score requires both the pre-result receipt and settlements')
    if args.receipt:
        def bounded(path: Path) -> dict:
            if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 30_000_000:
                raise ValueError('Result input missing or unbounded')
            value = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(value, dict):
                raise ValueError('Invalid result input')
            return value
        report = score(pair,market,forecast,quotes,decisions,args.source_dir,args.schedule,
                       history,bounded(args.receipt),bounded(args.settlements),
                       now=datetime.now(timezone.utc))
    else:
        report, _ = preflight(pair,market,forecast,quotes,decisions,
                              args.source_dir,args.schedule,history)
        report = freeze(report, decisions, now=datetime.now(timezone.utc))
        if report['record_sha256'] != EXPECTED_RECORD_SHA256:
            parser.error('Pre-result calibration receipt is already frozen')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,sort_keys=True,indent=2,allow_nan=False)
    print(json.dumps(report,sort_keys=True))


if __name__ == '__main__':
    main()
