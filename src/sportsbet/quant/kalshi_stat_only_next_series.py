"""Offline independent-game audit across committed NFL stat-only paper pairs.

When captures overlap, the earliest pregame pair owns the entire fixture.
Missing quotes, forecasts and outcomes in that pair never trigger a later
replacement. This research report cannot establish an executable edge.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from sportsbet.quant import kalshi_stat_only_next_eval as single
from sportsbet.quant import kalshi_stat_only_remote_anchor as remote_anchor
from sportsbet.quant import kalshi_role_shadow_v4 as role_v4
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_market_settlement import venue_results
from sportsbet.quant.kalshi_pair_capture import unpack
from sportsbet.quant.kalshi_pair_series_eval import _game_keys
from sportsbet.quant.kalshi_role_shadow_eval import _forward_bounds
from sportsbet.quant.kalshi_stat_only_forward_eval import _loss
from sportsbet.quant.kalshi_stat_only_win_uncertainty import _interval

VERSION = 'kalshi-nfl-stat-only-independent-series-v1'
MAX_CASES = 32
HIGH_PROBABILITY = Decimal('.75')


def _high_probability_diagnostic(selected: int, games: int,
                                 states: Counter[str], wins: list[tuple[str, int]],
                                 *, complete: bool, remote_verified: bool) -> dict:
    """Describe the fixed >=75% paper subset; never qualify consumer picks."""
    if (sum(states.values()) != selected or states['venue_verified'] != len(wins)
            or not 0 <= games <= selected or len({game for game, _ in wins}) > games):
        raise ValueError('High-probability candidate denominator changed')
    full = selected > 0 and len(wins) == selected
    interval = (_interval(wins) if full and games >= 2 else None)
    threshold = (complete and remote_verified and games >= 50 and interval is not None
                 and all(Decimal(interval[key][0]) > HIGH_PROBABILITY
                         for key in ('contract_weighted_95', 'equal_game_95')))
    return dict(high_probability_threshold=str(HIGH_PROBABILITY),
                high_probability_paper_candidates=selected,
                high_probability_independent_games=games,
                high_probability_result_states=dict(sorted(states.items())),
                high_probability_verified_subset_wins=sum(win for _, win in wins),
                high_probability_verified_subset_win_rate=(
                    str(Decimal(sum(win for _, win in wins))/len(wins)) if wins else None),
                high_probability_full_win_rate=(
                    str(Decimal(sum(win for _, win in wins))/selected) if full else None),
                high_probability_full_game_cluster_95=interval,
                descriptive_75pct_threshold_met=bool(threshold))


def _fixture_map(market: dict, cohort: dict) -> dict[str, tuple[str, ...]]:
    ids, fixtures = _game_keys(market, cohort)
    games = {row['milestone']['id']: row for row in
             market['evidence']['sources']['kalshi']['games']}
    by_id = {}
    for game_id in ids:
        game = games[game_id]
        teams = tuple(sorted((game['details']['home_team_id'],
                              game['details']['away_team_id'])))
        by_id[game_id] = (clock(game['start_date']).isoformat(), *teams)
    if set(by_id.values()) != fixtures:
        raise ValueError('Ambiguous exact fixture mapping')
    return by_id


def _bounds(rows: list[tuple], label: str) -> dict:
    if not rows:
        return {}
    comparator = 'market' if label == 'market' else 'prior20'
    return {key.replace('prior20', label): value
            for key, value in _forward_bounds(rows, comparator).items()}


def _favorable(bounds: dict, label: str) -> bool:
    return bool(bounds) and all(
        bounds.get(f'model_minus_{label}_{metric}_{cluster}_cluster_95')
        and Decimal(bounds[f'model_minus_{label}_{metric}_{cluster}_cluster_95'][1]) < 0
        for metric in ('brier', 'log_loss') for cluster in ('game', 'player'))


def _local(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError('Series path must be relative to the private manifest')
    path = (root/name).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Series path escapes the private manifest')
    return path


def aggregate(cases: list[dict], *, now: datetime,
              verify_remote: bool = False) -> dict:
    if now.utcoffset() is None or not 0 < len(cases) <= MAX_CASES:
        raise ValueError('Series clock or case count invalid')
    prepared = []
    model_artifact = implementation = None
    remote_reports = []
    for case in cases:
        required = {'inputs', 'source_dir', 'commitment', 'settlements'}
        optional = {'anchor_commit_oid', 'anchor_marker_path'}
        if not required <= set(case) or not set(case) <= required | optional:
            raise ValueError('Series case scope invalid')
        values, pre, prices = single.committed_preflight(
            case['inputs'], Path(case['source_dir']), case['commitment'])
        remote_pushed = None
        if verify_remote:
            if not optional <= set(case):
                raise ValueError('Remote pregame anchor missing')
            anchored = remote_anchor.verify(
                case['commitment'], case['anchor_commit_oid'],
                case['anchor_marker_path'])
            remote_reports.append(anchored)
            remote_pushed = clock(anchored['remote_pushed_at'])
        single.evaluate(case['inputs'], Path(case['source_dir']),
                        case['commitment'], case['settlements'], now=now)
        pair, market = values['pair'], values['market']
        cohort, role = unpack(pair)
        forecast = values['forecast']
        if role['protocol'] != role_v4.VERSION:
            raise ValueError('Series requires one current v4 source protocol')
        if model_artifact is None:
            model_artifact = forecast['frozen_model_artifact_sha256']
            implementation = forecast['frozen_implementation_sha256']
        elif (forecast['frozen_model_artifact_sha256'] != model_artifact
              or forecast['frozen_implementation_sha256'] != implementation):
            raise ValueError('Mixed stat-only artifacts cannot form one series')
        fixtures = _fixture_map(market, cohort)
        _, states = venue_results(market, cohort, case['settlements'], now=now)
        prepared.append((remote_pushed or clock(pair['started_at']),
                         digest(case['commitment']),
                         values, pre, prices, states, fixtures))
    prepared.sort(key=lambda row: (row[0], row[1]))
    seen_fixtures: set[tuple[str, ...]] = set()
    attempted_games = selected_games = duplicate_games = 0
    attempts = forecast_count = paired = 0
    result_states: Counter[str] = Counter()
    quote_states: Counter[str] = Counter()
    candidate_states: Counter[str] = Counter()
    game_pairs: set[tuple[str, ...]] = set()
    comparison = {label: [] for label in ('market', 'retained_history', 'strict_prior20')}
    candidate_wins: list[tuple[str, int]] = []
    high_wins: list[tuple[str, int]] = []
    high_states: Counter[str] = Counter()
    high_games: set[tuple[str, ...]] = set()
    high_selected = 0
    candidate_ask_cost = Decimal(0)
    selected_candidates = 0
    case_hashes = []
    for _, commitment_hash, values, pre, prices, states, fixtures in prepared:
        attempts += 1
        attempted_games += len(fixtures)
        owned = {game for game, fixture in fixtures.items() if fixture not in seen_fixtures}
        duplicate_games += len(fixtures)-len(owned)
        selected_games += len(owned)
        seen_fixtures.update(fixtures.values())
        case_hashes.append(commitment_hash)
        strict = {row['ticker']: row for row in values['control']['forecast_rows']}
        for row in values['forecast']['forecasts']:
            if row['milestone_id'] not in owned:
                continue
            ticker = row['ticker']
            forecast_count += 1
            state, outcome = states[ticker]
            result_states[state] += 1
            price_state, market_p, _, _ = prices[ticker]
            quote_states[price_state] += 1
            if state != 'venue_verified' or price_state != 'two_sided_exact':
                continue
            paired += 1
            game_pairs.add(fixtures[row['milestone_id']])
            actual = Decimal(1 if outcome == 'yes' else 0)
            model = _loss(Decimal(str(row['model_over_probability'])), actual)
            for label, probability in (
                    ('market', market_p),
                    ('retained_history', Decimal(str(row['unfitted_prior_probability']))),
                    ('strict_prior20', Decimal(str(strict[ticker]['prior20_over_probability'])))):
                baseline = _loss(probability, actual)
                comparison[label].append((str(fixtures[row['milestone_id']]),
                    row['gsis_player_id'], model[0]-baseline[0], model[1]-baseline[1]))
        for row in values['decisions']['candidates']:
            if row['milestone_id'] not in owned:
                continue
            selected_candidates += 1
            state, outcome = states[row['ticker']]
            candidate_states[state] += 1
            probability = Decimal(str(row['model_win_probability']))
            if not probability.is_finite() or not 0 < probability < 1:
                raise ValueError('Paper candidate probability invalid')
            high = probability >= HIGH_PROBABILITY
            if high:
                high_selected += 1
                high_games.add(fixtures[row['milestone_id']])
                high_states[state] += 1
            if state == 'venue_verified':
                candidate_wins.append((str(fixtures[row['milestone_id']]),
                                       int(outcome == row['side'])))
                if high:
                    high_wins.append((str(fixtures[row['milestone_id']]),
                                      int(outcome == row['side'])))
                candidate_ask_cost += Decimal(row['displayed_ask'])
    bounds = {label: _bounds(rows, label) for label, rows in comparison.items()}
    complete = (sum(result_states.values()) == forecast_count
                and result_states['venue_verified'] == forecast_count
                and quote_states['two_sided_exact'] == forecast_count
                and candidate_states['venue_verified'] == selected_candidates)
    enough_games = len(game_pairs) >= 50
    wins = sum(win for _, win in candidate_wins)
    paired_skill_signal = (complete and enough_games and all(
        _favorable(bounds[label], label) for label in comparison))
    remote_verified = verify_remote and len(remote_reports)==len(cases)
    high_report = _high_probability_diagnostic(
        high_selected, len(high_games), high_states, high_wins,
        complete=complete, remote_verified=remote_verified)
    return dict(protocol=VERSION, source_protocol=role_v4.VERSION,
        model_artifact_sha256=model_artifact,
        model_implementation_sha256=implementation,
        cohort_count=attempts, pregame_commitment_sha256=case_hashes,
        attempted_games=attempted_games, duplicate_games_excluded=duplicate_games,
        independent_selected_games=selected_games,
        selected_model_forecasts=forecast_count,
        forecast_result_states=dict(sorted(result_states.items())),
        forecast_quote_states=dict(sorted(quote_states.items())),
        paired_forecasts=paired, paired_independent_games=len(game_pairs),
        paired_bounds=bounds, complete=complete,
        minimum_50_independent_games_met=enough_games,
        paired_skill_signal=paired_skill_signal,
        probability_support=paired_skill_signal and remote_verified,
        paper_candidates=selected_candidates,
        candidate_result_states=dict(sorted(candidate_states.items())),
        verified_subset_wins=wins,
        verified_subset_win_rate=(str(Decimal(wins)/len(candidate_wins))
            if candidate_wins else None),
        full_candidate_win_rate=(str(Decimal(wins)/selected_candidates)
            if selected_candidates and len(candidate_wins)==selected_candidates else None),
        full_candidate_game_cluster_95=(
            _interval(candidate_wins) if selected_candidates and
            len(candidate_wins)==selected_candidates and
            len({game for game, _ in candidate_wins}) >= 2 else None),
        **high_report,
        verified_subset_gross_unit_profit=(str(Decimal(wins)-candidate_ask_cost)
            if candidate_wins else None),
        full_cohort_gross_unit_profit=(str(Decimal(wins)-candidate_ask_cost)
            if selected_candidates and len(candidate_wins)==selected_candidates else None),
        remote_pregame_anchor_verified=remote_verified,
        remote_anchor_commit_oid=[r['commit_oid'] for r in remote_reports],
        fills_verified=False,
        fees_verified=False, roi=None, clv=None, edge_established=False,
        qualified_picks=0, execution_ready=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Series output already exists')
    manifest, _ = single._input(args.manifest, 100_000)
    if (manifest.get('protocol') != VERSION
            or not 0 < len(manifest.get('cases', [])) <= MAX_CASES):
        parser.error('Invalid private series manifest')
    root = args.manifest.resolve().parent
    cases = []
    for row in manifest['cases']:
        if set(row) != set(single.LIMITS) | {'source_dir', 'commitment',
                                           'settlements', 'anchor_commit_oid',
                                           'anchor_marker_path'}:
            parser.error('Invalid series case path scope')
        inputs = {name: str(_local(root, row[name])) for name in single.LIMITS}
        commitment, _ = single._input(_local(root, row['commitment']), 10_000)
        settlements, _ = single._input(_local(root, row['settlements']), 30_000_000)
        cases.append(dict(inputs=inputs, source_dir=_local(root, row['source_dir']),
                          commitment=commitment, settlements=settlements,
                          anchor_commit_oid=row['anchor_commit_oid'],
                          anchor_marker_path=row['anchor_marker_path']))
    report = aggregate(cases, now=datetime.now(timezone.utc), verify_remote=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps({key: report[key] for key in (
        'protocol', 'cohort_count', 'independent_selected_games',
        'paired_independent_games', 'minimum_50_independent_games_met',
        'probability_support', 'edge_established', 'qualified_picks')},
        sort_keys=True))


if __name__ == '__main__':
    main()
