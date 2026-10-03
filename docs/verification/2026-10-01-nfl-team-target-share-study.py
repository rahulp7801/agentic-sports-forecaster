"""Private, retrospective NFL context research; no API or database access."""

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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stats', type=Path, required=True)
    parser.add_argument('--schedules', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    schedules = pl.read_parquet(args.schedules).filter(pl.col('game_type') == 'REG')
    schedule_by_game = {}
    for game in schedules.iter_rows(named=True):
        game_id = game['game_id']
        if game_id in schedule_by_game:
            raise ValueError('duplicate scheduled game')
        schedule_by_game[game_id] = game

    observations = []
    raw_counts = Counter()
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
        observations.append({'player': row['player_id'], 'season': row['season'],
                             'week': row['week'], 'game': row['game_id'],
                             'team': row['team'], 'day': date.fromisoformat(game['gameday']),
                             'targets': row['targets'], 'receptions': row['receptions']})

    duplicated = Counter((r['player'], r['game']) for r in observations)
    duplicate_keys = {key for key, n in duplicated.items() if n > 1}
    raw_counts['duplicate_player_game_rows'] = sum(duplicated[key] for key in duplicate_keys)
    observations = [r for r in observations if (r['player'], r['game']) not in duplicate_keys]

    team_total = Counter()
    team_members = defaultdict(dict)
    player_history = defaultdict(list)
    game_rows = {}
    for row in observations:
        key = (row['game'], row['team'])
        team_total[key] += row['targets']
        team_members[key][row['player']] = row['targets']
        player_history[row['player']].append(row)
        game_rows[row['player'], row['game']] = row
    for rows in player_history.values():
        rows.sort(key=lambda r: (r['day'], r['game']))

    examples, history_details = build_examples(observations, 'nfl', 'receptions')
    context_rows = []
    context_counts = Counter()
    example_counts = Counter(e.split for e in examples)
    cache = {}
    for example in examples:
        key = example.player, example.game
        if key not in cache:
            target = game_rows[key]
            prior = [r for r in player_history[example.player]
                     if r['day'] < target['day'] and r['team'] == target['team']][-5:]
            if len(prior) < 2:
                cache[key] = ('fewer_than_two_same_team_games', None)
            elif (target['day'] - prior[-1]['day']).days > 35:
                cache[key] = ('stale_same_team_history', None)
            elif any(team_total[r['game'], r['team']] <= 0 for r in prior):
                cache[key] = ('zero_team_targets', None)
            else:
                denominator = sum(team_total[r['game'], r['team']] for r in prior)
                own = sum(r['targets'] for r in prior)
                teammate_targets = Counter()
                for r in prior:
                    for player, targets in team_members[r['game'], r['team']].items():
                        if player != example.player:
                            teammate_targets[player] += targets
                top_teammate = max(teammate_targets.values(), default=0)
                if not (0 <= own <= denominator and 0 <= top_teammate <= denominator):
                    raise ValueError('impossible target share')
                cache[key] = ('eligible', (own / denominator, top_teammate / denominator))
        status, context = cache[key]
        context_counts[example.split + ':' + status] += 1
        if context is not None:
            context_rows.append(replace(example, features=example.features + context))

    plain_rows = [replace(e, features=e.features[:len(FEATURES)]) for e in context_rows]
    plain = {split: [e for e in plain_rows if e.split == split]
             for split in ('fit', 'select', 'evaluate')}
    context = {split: [e for e in context_rows if e.split == split]
               for split in ('fit', 'select', 'evaluate')}
    if any(len(plain[split]) < 100 or len({e.game for e in plain[split]}) < 10
           for split in plain):
        raise ValueError('insufficient split coverage')
    reference = fit_correction(plain['fit'], .1)
    challenger = fit_correction(context['fit'], .1)

    results = {}
    for split in ('select', 'evaluate'):
        base_p = reference.predict(plain[split])
        context_p = challenger.predict(context[split])
        results[split] = {
            'baseline': score(plain[split], base_p),
            'context': score(plain[split], context_p),
            'paired_context_minus_baseline': compare(plain[split], base_p, context_p),
        }
    result = {
        'status': 'retrospective_unpriced_research_only',
        'promotion': False,
        'protocol_sha256': digest(HERE / '2026-10-01-nfl-team-target-share-protocol.md'),
        'source_sha256': {'stats': digest(args.stats), 'schedules': digest(args.schedules)},
        'raw_regular_observations': len(observations),
        'raw_exclusions': dict(sorted(raw_counts.items())),
        'history_exclusions': history_details['excluded'],
        'all_research_examples': dict(sorted(example_counts.items())),
        'context_eligibility': dict(sorted(context_counts.items())),
        'eligible_by_split': {split: {'examples': len(plain[split]),
                                     'player_games': len({(e.player, e.game) for e in plain[split]}),
                                     'games': len({e.game for e in plain[split]})}
                              for split in plain},
        'features': list(FEATURES) + ['recent_team_target_share', 'top_other_recent_team_target_share'],
        'fit': {'l2': .1, 'baseline_coefficients': reference.coefficients.tolist(),
                'context_coefficients': challenger.coefficients.tolist()},
        'results': results,
        'limitations': ['research quantile lines, no matched sportsbook prices',
                        'historical archive may include later stat corrections',
                        'observed players only, no DNP census',
                        'no original pregame source versions or injury state'],
    }
    output = args.report
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('status', 'protocol_sha256',
          'source_sha256', 'raw_regular_observations', 'raw_exclusions',
          'all_research_examples', 'context_eligibility', 'eligible_by_split')}, indent=2))
    print(json.dumps({split: {'baseline_brier': value['baseline']['game_balanced_brier'],
                              'context_brier': value['context']['game_balanced_brier'],
                              'comparison': value['paired_context_minus_baseline']}
                      for split, value in results.items()}, indent=2))
    print(f'private_report={output}')


if __name__ == '__main__':
    main()
