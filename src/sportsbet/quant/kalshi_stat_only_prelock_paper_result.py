"""Post-result paper accounting for the frozen NFL stat-only prelock cohort.

The original 70 decisions remain fixed. Costs are hypothetical one-contract
fills at later displayed asks; venue results are exact public final contracts.
This audit makes no network request and never promotes consumer picks.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
from pathlib import Path

from sportsbet.quant import kalshi_market_settlement as venue
from sportsbet.quant.clock_attestation import (
    HOSTS, MAX_BETWEEN_HOST_OFFSETS_SECONDS, MAX_OFFSET_SECONDS,
    MAX_RTT_SECONDS, VERSION as CLOCK_VERSION,
)
from sportsbet.quant import kalshi_stat_only_prelock_fee_cohort as fee_cohort
from sportsbet.quant import kalshi_stat_only_prelock_fee_score as fee_score
from sportsbet.quant import kalshi_stat_only_settlement_capture as capture
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_pair_capture import unpack
from sportsbet.quant.kalshi_stat_only_forward_eval import _pinned, preflight

VERSION = 'kalshi-nfl-stat-only-prelock-paper-result-v1'


def score_results(decisions: dict, cost_report: dict,
                  venue_states: dict[str, tuple[str, str | None]],
                  *, settlement_sha256: str) -> dict:
    """Preserve every original decision in outcome and cost denominators."""
    candidates = decisions['candidates']
    if (len(candidates) != decisions['candidates_count'] or len(candidates) != 70
            or digest(candidates) != decisions['candidates_sha256']):
        raise ValueError('Frozen candidate commitment changed')
    if (cost_report.get('protocol') != fee_cohort.VERSION
            or cost_report.get('frozen_candidates') != 70
            or cost_report.get('frozen_kickoff_groups') != 6
            or sum(cost_report.get('candidate_states', {}).values()) != 70
            or cost_report.get('modeled_one_contract_costs') !=
                cost_report['candidate_states'].get('one_contract_cost_modeled', 0)):
        raise ValueError('Full fee/quote denominator changed')
    if not isinstance(settlement_sha256, str) or len(settlement_sha256) != 64:
        raise ValueError('Settlement commitment missing')
    if not set(row['ticker'] for row in candidates) <= set(venue_states):
        raise ValueError('Venue result states missed frozen candidates')
    if len({row['ticker'] for row in candidates}) != 70:
        raise ValueError('Duplicate frozen decision')
    states = Counter()
    wins = 0
    verified_games = set()
    for candidate in candidates:
        state, outcome = venue_states[candidate['ticker']]
        if state == 'venue_verified':
            if outcome not in ('yes', 'no'):
                raise ValueError('Verified venue result is not binary')
            if candidate['side'] not in ('yes', 'no'):
                raise ValueError('Frozen side is not binary')
            wins += outcome == candidate['side']
            verified_games.add(candidate['milestone_id'])
        elif outcome is not None:
            raise ValueError('Unverified venue result carries an outcome')
        states[state] += 1
    verified = states['venue_verified']
    if sum(states.values()) != 70:
        raise ValueError('Venue result denominator changed')
    complete_results = verified == 70
    complete_costs = cost_report['complete_cost_scenario'] is True
    if complete_costs != (cost_report['modeled_one_contract_costs'] == 70):
        raise ValueError('Full cost scenario flag changed')
    direct = cost_report['full_cohort_direct_total_cost'] if complete_costs else None
    nondirect = cost_report['full_cohort_nondirect_total_cost'] if complete_costs else None
    if complete_costs and (direct is None or nondirect is None):
        raise ValueError('Full cost totals missing')
    return {'protocol': VERSION, 'frozen_candidates': 70,
            'verified_result_candidates': verified,
            'verified_result_games': len(verified_games),
            'result_states': dict(sorted(states.items())),
            'verified_subset_wins': wins,
            'verified_subset_win_rate': str(Decimal(wins)/verified) if verified else None,
            'complete_results': complete_results,
            'full_cohort_wins': wins if complete_results else None,
            'full_cohort_win_rate': str(Decimal(wins)/70) if complete_results else None,
            'costed_candidates': cost_report['modeled_one_contract_costs'],
            'complete_cost_scenario': complete_costs,
            'full_cohort_hypothetical_direct_unit_profit':
                str(Decimal(wins)-Decimal(direct))
                if complete_results and complete_costs else None,
            'full_cohort_hypothetical_nondirect_unit_profit':
                str(Decimal(wins)-Decimal(nondirect))
                if complete_results and complete_costs else None,
            'settlement_evidence_sha256': settlement_sha256,
            'fee_quote_group_reports_sha256': cost_report['group_reports_sha256'],
            'later_prelock_price_assumed': True, 'single_fill_assumed': True,
            'actual_fills_verified': False, 'roi': None, 'clv': None,
            'repeatable_edge_established': False, 'qualified_picks': 0}


def verify_capture_wrapper(settlement: dict, pre: dict) -> None:
    """Bind full-result read to its postgame capture clock and frozen scope."""
    if (settlement.get('protocol') != capture.VERSION
            or settlement.get('original_market_contracts') !=
                pre['original_market_contracts']
            or settlement.get('first_eligible_settlement_at') !=
                pre['first_eligible_settlement_at']
            or settlement.get('record_sha256') != digest({
                key: value for key, value in settlement.items()
                if key != 'record_sha256'})):
        raise ValueError('Exact venue capture wrapper or commitment changed')
    evidence = settlement['evidence']
    pages = evidence['pages']
    proof = settlement['clock_proof']
    gate = clock(pre['first_eligible_settlement_at'])
    checked = clock(proof['checked_at'])
    first = clock(pages[0]['request_started_at'])
    last = max(clock(page['received_at']) for page in pages)
    if (proof.get('protocol') != CLOCK_VERSION
            or proof.get('local_clock_acceptable') is not True
            or not isinstance(proof.get('observations'), list)
            or [row.get('host') for row in proof['observations']] != list(HOSTS)
            or not gate <= checked <= first <= last <= clock(settlement['captured_at'])
            or (first-checked).total_seconds() > 120):
        raise ValueError('Exact venue capture gate or clock proof changed')
    offsets = []
    for row in proof['observations']:
        started = clock(row['request_started_at'])
        received = clock(row['response_received_at'])
        server = clock(row['server_date'])
        rtt = (received-started).total_seconds()
        offset = (server-(started+(received-started)/2)).total_seconds()
        age = row.get('age')
        uncached = (age is None or (type(age) is str and age == '0')
                    or (type(age) is int and age == 0))
        if (not started <= received <= checked
                or not 0 <= rtt <= MAX_RTT_SECONDS
                or not math.isfinite(offset) or abs(offset) > MAX_OFFSET_SECONDS
                or row.get('http_status') != 200 or not uncached
                or type(row.get('rtt_seconds')) not in (int, float)
                or type(row.get('server_minus_local_seconds')) not in (int, float)
                or not math.isfinite(row['rtt_seconds'])
                or not math.isfinite(row['server_minus_local_seconds'])
                or abs(row['rtt_seconds']-rtt) > .001
                or abs(row['server_minus_local_seconds']-offset) > .001):
            raise ValueError('Exact venue capture clock observation changed')
        offsets.append(offset)
    if abs(offsets[0]-offsets[1]) > MAX_BETWEEN_HOST_OFFSETS_SECONDS:
        raise ValueError('Independent venue capture clocks disagree')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pair', 'market', 'forecast', 'quotes', 'decisions'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    parser.add_argument('--receipt-dir', type=Path, required=True)
    parser.add_argument('--settlements', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Paper-result output already exists')
    pair, market, forecast, quotes, decisions = (
        _pinned(getattr(args, name), name) for name in
        ('pair', 'market', 'forecast', 'quotes', 'decisions'))
    pre, _ = preflight(pair, market, forecast, quotes, decisions,
                       args.source_dir, args.schedule)
    now = datetime.now(timezone.utc)
    if now < clock(pre['first_eligible_settlement_at']):
        parser.error('Before full-cohort result gate; no settlement input read')
    if args.receipt_dir.is_symlink() or not args.receipt_dir.is_dir():
        parser.error('Fee/quote receipt directory missing or symlinked')
    receipts = {}
    for kickoff in fee_cohort.groups(forecast, decisions):
        fee_path, quote_path = fee_cohort._paths(args.receipt_dir, kickoff)
        receipts[kickoff] = tuple(
            fee_score._receipt(path) if path.exists() or path.is_symlink() else None
            for path in (fee_path, quote_path))
    cost_report = fee_cohort.evaluate(market, forecast, decisions, receipts)
    settlement = fee_score._receipt(args.settlements)
    verify_capture_wrapper(settlement, pre)
    cohort, _ = unpack(pair)
    _, states = venue.venue_results(market, cohort, settlement, now=now)
    report = score_results(decisions, cost_report, states,
                           settlement_sha256=settlement['evidence_sha256'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
