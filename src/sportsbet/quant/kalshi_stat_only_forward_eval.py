"""Precommitted read-only scorer for the October 4 NFL stat-only Kalshi paper cohort.

The exact input hashes were published before any selected game. This module
never collects prices, places orders, or promotes a consumer recommendation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from sportsbet.quant import kalshi_role_shadow_v2 as role_v3
from sportsbet.quant.kalshi_ask_policy import decision, one_per_player_game
from sportsbet.quant.kalshi_exact_markout import _market_state, _side_asks
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_market_settlement import venue_results, verify_cohort
from sportsbet.quant.kalshi_pair_capture import unpack
from sportsbet.quant.kalshi_role_shadow_eval import _forward_bounds
from sportsbet.quant.nfl_stat_only_shadow import (ARTIFACT_SHA256, FROZEN_AT,
    VERSION as MODEL_VERSION, implementation_sha256)

VERSION = 'kalshi-nfl-stat-only-forward-score-v1'
SCHEDULE_SHA256 = '4f27270efeba3af862d250a821ff00578da1ce158b76576b72aa283751b22662'
EXPECTED_SHA256 = {
    'pair': '8df6075f9794837f9c99772cf70d5dbdfb7954a07421ebfda0345494637e9acb',
    'market': '05b2c78304cb80c7923bf530e1b2a8a9b3e30ce9f19d1d164d72944c878f29fc',
    'forecast': '649de1f5595c2dcf789050d63d9612375b2d4cae29751943697db62a52368d58',
    'quotes': '66dea5d6c5399501f053cab255c381bf78b9d15c1bebb7f658235bad80b1275f',
    'decisions': '81646fd99f2f57cb70ec5b60a9889de93d2d86f99017ca3150b71e2c7df4987e',
}
MAX_BYTES = {'pair': 5_000_000, 'market': 25_000_000,
             'forecast': 500_000, 'quotes': 2_000_000, 'decisions': 500_000}


def _pinned(path: Path, name: str) -> dict:
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= MAX_BYTES[name]):
        raise ValueError(f'{name} receipt missing or unbounded')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256[name]:
        raise ValueError(f'{name} pre-result commitment changed')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f'{name} receipt is not an object')
    return value


def _price_states(original: dict, forecast: dict, quotes: dict,
                  decided_at: datetime) -> dict[str, tuple[str, Decimal | None, dict | None, str | None]]:
    rows = forecast['forecasts']
    tickers = sorted(row['ticker'] for row in rows)
    evidence = quotes['evidence']
    generated = clock(forecast['generated_at'])
    first_lock = min(clock(row['scheduled_game_start_time'])-timedelta(hours=1) for row in rows)
    if (len(tickers) != len(set(tickers)) or len(tickers) != forecast['predicted_contracts']
            or evidence.get('protocol') != 'kalshi-nfl-stat-only-exact-quote-v1'
            or quotes.get('evidence_sha256') != digest(evidence)
            or evidence.get('forecast_sha256') != forecast['forecast_sha256']
            or evidence.get('forecast_receipt_sha256') != digest(forecast)
            or evidence.get('requested_tickers') != tickers
            or not isinstance(evidence.get('pages'), list)
            or len(evidence['pages']) != (len(tickers)+19)//20
            or not generated < clock(evidence['captured_at']) <= decided_at < first_lock
            or (decided_at-generated).total_seconds() > 300):
        raise ValueError('Post-freeze quote scope or chronology changed')
    fetched = {}
    received_at = {}
    for index, page in enumerate(evidence['pages']):
        batch = tickers[index*20:(index+1)*20]
        started, received = clock(page['request_started_at']), clock(page['received_at'])
        if (page.get('tickers') != batch or not generated < started <= received
                <= clock(evidence['captured_at']) or received >= first_lock
                or (received-generated).total_seconds() > 300):
            raise ValueError('Exact quote batch chronology changed')
        if 'error_type' in page:
            if 'body' in page or not isinstance(page['error_type'], str):
                raise ValueError('Conflicting exact quote page')
            for ticker in batch:
                received_at[ticker] = page['received_at']
            continue
        body = page['body']
        markets = body.get('markets') if isinstance(body, dict) else None
        if (not isinstance(markets, list) or body.get('cursor') not in (None, '')
                or any(not isinstance(market, dict) for market in markets)):
            raise ValueError('Incomplete exact quote response')
        returned = [market.get('ticker') for market in markets]
        if (len(returned) != len(set(returned)) or not set(returned) <= set(batch)):
            raise ValueError('Extra or duplicate exact quote')
        fetched.update({market['ticker']: market for market in markets})
        for ticker in batch:
            received_at[ticker] = page['received_at']
    originals = {row['ticker']: row for row in
                 original['evidence']['sources']['kalshi']['prop_inventory']['quotes']}
    states = {}
    for ticker in tickers:
        market = fetched.get(ticker)
        if market is None:
            states[ticker] = ('missing_or_failed', None, None, received_at[ticker])
            continue
        yes_state, yes = _market_state(market, originals[ticker], 'yes')
        no_state, no = _market_state(market, originals[ticker], 'no')
        if yes_state != 'prelock_exact_ask' or no_state != 'prelock_exact_ask':
            states[ticker] = (f'{yes_state}|{no_state}', None, None, received_at[ticker])
            continue
        sides = _side_asks(market)
        midpoint = (Decimal(1)-no+yes)/2
        if not 0 < midpoint < 1:
            raise ValueError('Invalid matched market midpoint')
        asks = {'yes_ask': {'cost': str(yes), 'displayed_size': str(sides['yes'][1])},
                'no_ask': {'cost': str(no), 'displayed_size': str(sides['no'][1])}}
        states[ticker] = ('two_sided_exact', midpoint, asks, received_at[ticker])
    return states


def preflight(pair: dict, original: dict, forecast: dict, quotes: dict,
              decisions: dict, source_dir: Path, schedule_path: Path) -> tuple[dict, dict]:
    if (schedule_path.is_symlink() or not schedule_path.is_file()
            or not 0 < schedule_path.stat().st_size <= 1_000_000
            or hashlib.sha256(schedule_path.read_bytes()).hexdigest() != SCHEDULE_SHA256):
        raise ValueError('Pinned prequote schedule changed')
    cohort, shadow = unpack(pair)
    verify_cohort(original, cohort)
    if (shadow['protocol'] != role_v3.VERSION
            or role_v3.build_report(original, cohort, source_dir,
                                    shadow['source_manifest'],
                                    now=clock(shadow['generated_at'])) != shadow
            or forecast.get('protocol') != 'kalshi-nfl-stat-only-forward-transfer-v1'
            or forecast.get('frozen_model_version') != MODEL_VERSION
            or forecast.get('frozen_model_artifact_sha256') != ARTIFACT_SHA256
            or forecast.get('frozen_implementation_sha256') != implementation_sha256()
            or forecast.get('schedule_source_sha256') != SCHEDULE_SHA256
            or forecast.get('source_manifest_sha256') != digest(shadow['source_manifest'])
            or clock(forecast['generated_at']) < clock(FROZEN_AT)
            or forecast.get('source_forecasts_sha256') != shadow['forecasts_sha256']
            or forecast.get('market_selection_sha256') != cohort['selection_sha256']
            or forecast.get('forecast_sha256') != digest(forecast['forecasts'])
            or decisions.get('protocol') != 'kalshi-nfl-stat-only-ask-paper-v1'
            or decisions.get('minimum_gross_margin') != '0.05'
            or decisions.get('model_receipt_sha256') != digest(forecast)
            or decisions.get('quote_receipt_sha256') != digest(quotes)
            or decisions.get('model_forecast_sha256') != forecast['forecast_sha256']):
        raise ValueError('Frozen model, source, or paper receipt changed')
    eligible = [row for row in shadow['forecasts']
                if row['prop_type'] in ('rec_yds', 'receptions')]
    rows = forecast['forecasts']
    if (forecast['eligible_contracts'] != len(eligible)
            or forecast['predicted_contracts'] + sum(forecast['unavailable_reasons'].values())
            != len(eligible) or not {r['ticker'] for r in rows} <=
            {r['ticker'] for r in eligible}
            or decisions['eligible_model_contracts'] != len(eligible)
            or decisions['model_forecasts'] != len(rows)):
        raise ValueError('Frozen transfer denominator changed')
    decided_at = clock(decisions['decided_at'])
    prices = _price_states(original, forecast, quotes, decided_at)
    offers = {row['ticker']: row for row in cohort['selections']}
    available = []
    counts = Counter()
    for row in rows:
        ticker = row['ticker']
        offer = offers[ticker]
        state, _, asks, received = prices[ticker]
        if (row['prop_type'] != offer['prop_type'] or row['line'] != offer['line']
                or row['milestone_id'] != offer['milestone_id']
                or row['scheduled_game_start_time'] != offer['scheduled_game_start_time']):
            raise ValueError('Transfer exact contract identity changed')
        if asks is None:
            counts[state] += 1
            continue
        chosen = decision(dict(offer, **asks), row)
        if chosen is None:
            counts['below_5pp'] += 1
        else:
            chosen['price_received_at'] = received
            chosen['model_version'] = forecast['frozen_model_version']
            available.append(chosen)
            counts['above_5pp'] += 1
    candidates = one_per_player_game(available)
    if (sum(counts.values()) != len(rows)
            or dict(sorted(counts.items())) != decisions['quote_state_counts']
            or len(available) != decisions['above_margin_before_cap']
            or len(available)-len(candidates) != decisions['one_per_player_game_excluded']
            or candidates != decisions['candidates']
            or digest(candidates) != decisions['candidates_sha256']
            or len(candidates) != decisions['candidates_count']
            or len({r['milestone_id'] for r in candidates}) != decisions['candidate_games']):
        raise ValueError('Fixed ask policy or full denominator changed')
    report = dict(protocol=VERSION,
        original_market_contracts=len(cohort['selections']),
        receiving_source_contracts=len(eligible),
        model_forecasts=len(rows),
        model_unavailable=dict(sorted(forecast['unavailable_reasons'].items())),
        quote_states=dict(sorted(counts.items())),
        paper_candidates=len(candidates),
        paper_games=decisions['candidate_games'],
        forecast_sha256=forecast['forecast_sha256'],
        candidates_sha256=decisions['candidates_sha256'],
        first_eligible_settlement_at=(max(clock(row['scheduled_game_start_time'])
            for row in cohort['selections'])+timedelta(hours=6)).isoformat(),
        authenticated_settlements=0, edge_established=False,
        qualified_picks=0, execution_ready=False)
    return report, prices


def _loss(p: Decimal, outcome: Decimal) -> tuple[Decimal, Decimal]:
    if not p.is_finite() or not 0 < p < 1:
        raise ValueError('Invalid probability in frozen score')
    return (p-outcome)**2, -(outcome*p.ln()+(1-outcome)*(1-p).ln())


def score_states(forecast: dict, decisions: dict, prices: dict,
                 states: dict[str, tuple[str, str | None]],
                 *, full_contracts: int, settlement_sha256: str) -> dict:
    """Score every frozen attempt; missing venue or quote evidence stays visible."""
    forecast_counts = Counter()
    candidate_counts = Counter()
    paired_market = []
    paired_prior = []
    model_scores = []
    market_scores = []
    prior_scores = []
    sensitivity = {name: {'forecast_contracts': 0, 'paired_results': 0,
        'model_brier': [], 'market_brier': [], 'prior_brier': [],
        'model_log_loss': [], 'market_log_loss': [], 'prior_log_loss': [],
        'paper_candidates': 0, 'verified_candidates': 0,
        'verified_wins': 0, 'verified_ask_cost': Decimal(0)}
        for name in ('snap_backed_zero', 'no_snap_backed_zero')}
    by_ticker = {row['ticker']: row for row in forecast['forecasts']}
    for row in forecast['forecasts']:
        ticker = row['ticker']
        zero_count = row['snap_backed_zeros']
        if type(zero_count) is not int or zero_count < 0:
            raise ValueError('Invalid frozen snap-backed zero count')
        bucket = sensitivity['snap_backed_zero' if zero_count else 'no_snap_backed_zero']
        bucket['forecast_contracts'] += 1
        state, outcome = states[ticker]
        forecast_counts[state] += 1
        price_state, market_p, _, _ = prices[ticker]
        if state != 'venue_verified' or price_state != 'two_sided_exact':
            continue
        yes = Decimal(1 if outcome == 'yes' else 0)
        model = _loss(Decimal(str(row['model_over_probability'])), yes)
        market = _loss(market_p, yes)
        prior = _loss(Decimal(str(row['unfitted_prior_probability'])), yes)
        model_scores.append(model)
        market_scores.append(market)
        prior_scores.append(prior)
        bucket['paired_results'] += 1
        bucket['model_brier'].append(model[0])
        bucket['market_brier'].append(market[0])
        bucket['prior_brier'].append(prior[0])
        bucket['model_log_loss'].append(model[1])
        bucket['market_log_loss'].append(market[1])
        bucket['prior_log_loss'].append(prior[1])
        player = row['gsis_player_id']
        game = row['milestone_id']
        paired_market.append((game, player, model[0]-market[0], model[1]-market[1]))
        paired_prior.append((game, player, model[0]-prior[0], model[1]-prior[1]))
    paid = Decimal(0)
    wins = 0
    candidate_games = set()
    for row in decisions['candidates']:
        zero_count = by_ticker[row['ticker']]['snap_backed_zeros']
        bucket = sensitivity['snap_backed_zero' if zero_count else 'no_snap_backed_zero']
        bucket['paper_candidates'] += 1
        state, outcome = states[row['ticker']]
        candidate_counts[state] += 1
        if state == 'venue_verified':
            candidate_games.add(row['milestone_id'])
            paid += Decimal(row['displayed_ask'])
            wins += int(outcome == row['side'])
            bucket['verified_candidates'] += 1
            bucket['verified_wins'] += int(outcome == row['side'])
            bucket['verified_ask_cost'] += Decimal(row['displayed_ask'])
    sensitivity_report = {}
    for name, bucket in sensitivity.items():
        paired = bucket['paired_results']
        verified = bucket['verified_candidates']
        sensitivity_report[name] = dict(
            forecast_contracts=bucket['forecast_contracts'], paired_results=paired,
            paired_model_brier=str(sum(bucket['model_brier'])/paired) if paired else None,
            paired_market_brier=str(sum(bucket['market_brier'])/paired) if paired else None,
            paired_prior_brier=str(sum(bucket['prior_brier'])/paired) if paired else None,
            paired_model_log_loss=str(sum(bucket['model_log_loss'])/paired) if paired else None,
            paired_market_log_loss=str(sum(bucket['market_log_loss'])/paired) if paired else None,
            paired_prior_log_loss=str(sum(bucket['prior_log_loss'])/paired) if paired else None,
            paper_candidates=bucket['paper_candidates'], verified_candidates=verified,
            verified_wins=bucket['verified_wins'],
            verified_subset_win_rate=str(Decimal(bucket['verified_wins'])/verified)
                if verified else None,
            verified_subset_gross_unit_profit=str(Decimal(bucket['verified_wins'])-
                bucket['verified_ask_cost']) if verified else None,
            full_bucket_gross_unit_profit=str(Decimal(bucket['verified_wins'])-
                bucket['verified_ask_cost']) if verified and verified==bucket['paper_candidates'] else None)
    bounds_market = _forward_bounds(paired_market, 'market') if paired_market else {}
    bounds_prior = _forward_bounds(paired_prior, 'prior20') if paired_prior else {}
    bounds = bounds_market | bounds_prior
    all_forecast_verified = forecast_counts['venue_verified'] == len(forecast['forecasts'])
    all_prices_valid = sum(state == 'two_sided_exact' for state, _, _, _ in prices.values()) == len(prices)
    enough_games = len({game for game, _, _, _ in paired_market}) >= 50
    favor_both = bool(bounds) and all(
        bounds.get(f'model_minus_{comparator}_{metric}_{cluster}_cluster_95')
        and Decimal(bounds[f'model_minus_{comparator}_{metric}_{cluster}_cluster_95'][1]) < 0
        for comparator in ('market', 'prior20')
        for metric in ('brier', 'log_loss') for cluster in ('game', 'player'))
    return dict(protocol=VERSION, original_market_contracts=full_contracts,
        receiving_source_contracts=forecast['eligible_contracts'],
        model_forecasts=len(forecast['forecasts']),
        forecast_result_counts=dict(sorted(forecast_counts.items())),
        two_sided_paired_results=len(paired_market),
        two_sided_paired_games=len({game for game, _, _, _ in paired_market}),
        paired_model_brier=str(sum(x[0] for x in model_scores)/len(model_scores)) if model_scores else None,
        paired_market_brier=str(sum(x[0] for x in market_scores)/len(market_scores)) if market_scores else None,
        paired_prior_brier=str(sum(x[0] for x in prior_scores)/len(prior_scores)) if prior_scores else None,
        paired_bounds=bounds,
        probability_support=(all_forecast_verified and all_prices_valid
                             and enough_games and favor_both),
        paper_candidates=decisions['candidates_count'],
        paper_candidate_games=decisions['candidate_games'],
        candidate_result_counts=dict(sorted(candidate_counts.items())),
        snap_backed_zero_sensitivity=sensitivity_report,
        verified_candidate_games=len(candidate_games),
        verified_subset_gross_unit_profit=str(Decimal(wins)-paid)
            if candidate_counts['venue_verified'] else None,
        full_cohort_gross_unit_profit=str(Decimal(wins)-paid)
            if candidate_counts['venue_verified'] == decisions['candidates_count'] else None,
        settlement_evidence_sha256=settlement_sha256,
        fills_verified=False, fees_verified=False, roi=None, clv=None,
        edge_established=False, qualified_picks=0, execution_ready=False)


def evaluate(pair: dict, original: dict, forecast: dict, quotes: dict,
             decisions: dict, source_dir: Path, schedule_path: Path, settlements: dict,
             *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    pre, prices = preflight(pair, original, forecast, quotes, decisions, source_dir, schedule_path)
    if now.utcoffset() is None or now < clock(pre['first_eligible_settlement_at']):
        raise ValueError('Exact result audit is premature')
    cohort, _ = unpack(pair)
    selection, states = venue_results(original, cohort, settlements, now=now)
    result = score_states(forecast, decisions, prices, states,
                          full_contracts=len(selection),
                          settlement_sha256=settlements['evidence_sha256'])
    result['full_venue_result_counts'] = dict(sorted(Counter(
        state for state, _ in states.values()).items()))
    if sum(result['full_venue_result_counts'].values()) != pre['original_market_contracts']:
        raise AssertionError('Original exact-contract result denominator changed')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair', 'market', 'forecast', 'quotes', 'decisions'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--settlements', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Output already exists')
    pair, market, forecast, quotes, decisions = (
        _pinned(getattr(args, name), name) for name in
        ('pair', 'market', 'forecast', 'quotes', 'decisions'))
    if args.settlements:
        path = args.settlements
        if (path.is_symlink() or not path.is_file()
                or not 0 < path.stat().st_size <= 30_000_000):
            parser.error('Settlement receipt missing or unbounded')
        settlements = json.loads(path.read_text(encoding='utf-8'))
        report = evaluate(pair, market, forecast, quotes, decisions,
                          args.source_dir, args.schedule, settlements)
    else:
        report, _ = preflight(pair, market, forecast, quotes, decisions,
                              args.source_dir, args.schedule)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
