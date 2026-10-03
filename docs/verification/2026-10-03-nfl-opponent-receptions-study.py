"""Offline NFL opponent-receptions study; aggregate-only, no network or database."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path

import polars as pl

from sportsbet.quant.history_features import FEATURES
from sportsbet.quant.history_tuning import build_examples, compare, fit_correction, score

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / '2026-10-03-nfl-opponent-receptions-protocol.md'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stats', type=Path, required=True)
    parser.add_argument('--schedules', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    schedules = pl.read_parquet(args.schedules).filter(
        (pl.col('game_type') == 'REG') & pl.col('season').is_between(2023, 2025))
    schedule_by_game = {}
    for game in schedules.iter_rows(named=True):
        if game['game_id'] in schedule_by_game:
            raise ValueError('duplicate scheduled game')
        schedule_by_game[game['game_id']] = game

    raw_counts = Counter()
    observations = []
    for row in pl.read_parquet(args.stats).filter(pl.col('season_type') == 'REG').select(
            'player_id', 'season', 'week', 'game_id', 'team', 'targets', 'receptions').iter_rows(named=True):
        game = schedule_by_game.get(row['game_id'])
        if game is None or row['season'] != game['season'] or row['week'] != game['week']:
            raw_counts['missing_or_inexact_schedule'] += 1
            continue
        if row['team'] not in (game['home_team'], game['away_team']):
            raw_counts['team_mismatch'] += 1
            continue
        if row['player_id'] is None:
            raw_counts['missing_player_id'] += 1
            continue
        if row['targets'] is None or row['receptions'] is None or row['targets'] < 0 or row['receptions'] < 0:
            raw_counts['invalid_category'] += 1
            continue
        observations.append({'player': str(row['player_id']), 'season': row['season'],
                             'week': row['week'], 'game': row['game_id'],
                             'team': row['team'], 'day': date.fromisoformat(game['gameday']),
                             'targets': row['targets'], 'receptions': row['receptions']})

    duplicates = Counter((r['player'], r['game']) for r in observations)
    duplicate_keys = {key for key, count in duplicates.items() if count > 1}
    raw_counts['duplicate_player_game_rows'] = sum(duplicates[key] for key in duplicate_keys)
    observations = [r for r in observations if (r['player'], r['game']) not in duplicate_keys]
    player_game = {(r['player'], r['game']): r for r in observations}
    if len(player_game) != len(observations):
        raise ValueError('duplicate player/game remained')

    team_receptions = Counter()
    for row in observations:
        team_receptions[row['game'], row['team']] += row['receptions']
    defense_history = defaultdict(list)
    defense_counts = Counter()
    for game in schedule_by_game.values():
        home, away, game_id = game['home_team'], game['away_team'], game['game_id']
        if home is None or away is None or home == away:
            defense_counts['invalid_team_identity'] += 1
            continue
        home_received = team_receptions[game_id, home]
        away_received = team_receptions[game_id, away]
        if home_received <= 0 or away_received <= 0:
            defense_counts['missing_or_nonpositive_opposing_receptions'] += 1
            continue
        day = date.fromisoformat(game['gameday'])
        defense_history[home].append((game['season'], day, game_id, away_received))
        defense_history[away].append((game['season'], day, game_id, home_received))
    for rows in defense_history.values():
        rows.sort(key=lambda row: (row[1], row[2]))

    examples, history_details = build_examples(observations, 'nfl', 'receptions')
    eligibility = Counter()
    included = []
    context_cache = {}
    for example in examples:
        key = (example.player, example.game)
        if key not in context_cache:
            target = player_game[key]
            game = schedule_by_game[example.game]
            opponent = game['away_team'] if target['team'] == game['home_team'] else game['home_team']
            prior = [r for r in defense_history[opponent]
                     if r[0] == target['season'] and r[1] < target['day']][-5:]
            if len(prior) < 3:
                context_cache[key] = ('fewer_than_three_opponent_games', None)
            elif (target['day'] - prior[-1][1]).days > 35:
                context_cache[key] = ('stale_opponent_history', None)
            else:
                context_cache[key] = ('eligible', sum(r[3] for r in prior) / len(prior))
        state, allowed = context_cache[key]
        eligibility[example.split + ':' + state] += 1
        if allowed is not None:
            included.append(replace(example, features=example.features + (allowed,)))

    context = {split: [e for e in included if e.split == split]
               for split in ('fit', 'select', 'evaluate')}
    baseline = {split: [replace(e, features=e.features[:len(FEATURES)])
                        for e in context[split]]
                for split in context}
    if any(len(baseline[split]) < 100 or len({e.game for e in baseline[split]}) < 10
           for split in baseline):
        raise ValueError('insufficient split coverage')
    base_fit = fit_correction(baseline['fit'], .1)
    opponent_fit = fit_correction(context['fit'], .1)
    results = {}
    for split in ('select', 'evaluate'):
        base_p = base_fit.predict(baseline[split])
        opponent_p = opponent_fit.predict(context[split])
        results[split] = {'baseline': score(baseline[split], base_p),
                          'opponent': score(baseline[split], opponent_p),
                          'paired_opponent_minus_baseline': compare(baseline[split], base_p, opponent_p)}
    report = {
        'status': 'retrospective_unpriced_research_only', 'promotion': False,
        'protocol_sha256': digest(PROTOCOL),
        'source_sha256': {'stats': digest(args.stats), 'schedules': digest(args.schedules)},
        'raw_observations': len(observations),
        'raw_exclusions': dict(sorted(raw_counts.items())),
        'defense_exclusions': dict(sorted(defense_counts.items())),
        'history_exclusions': history_details['excluded'],
        'context_eligibility': dict(sorted(eligibility.items())),
        'eligible_by_split': {split: {'examples': len(baseline[split]),
                                     'player_games': len({(e.player, e.game) for e in baseline[split]}),
                                     'games': len({e.game for e in baseline[split]})}
                              for split in baseline},
        'features': list(FEATURES) + ['opponent_recent_receptions_allowed'],
        'fit': {'l2': .1, 'baseline_coefficients': base_fit.coefficients.tolist(),
                'opponent_coefficients': opponent_fit.coefficients.tolist()},
        'results': results,
        'limitations': ['synthetic research lines, no matched executable historical prices',
                        'historical archives may include later stat corrections',
                        'observed participants only, no DNP census or injury state',
                        'prior 2025 outcomes for other hypotheses were inspected'],
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'protocol_sha256': report['protocol_sha256'],
                      'source_sha256': report['source_sha256'],
                      'eligible_by_split': report['eligible_by_split'],
                      'context_eligibility': report['context_eligibility'],
                      'results': {s: {'baseline_brier': v['baseline']['game_balanced_brier'],
                                      'opponent_brier': v['opponent']['game_balanced_brier'],
                                      'paired': v['paired_opponent_minus_baseline']}
                                  for s, v in results.items()}}, indent=2))


if __name__ == '__main__':
    main()
