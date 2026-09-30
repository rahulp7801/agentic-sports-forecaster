"""Offline accuracy/calibration and recent-form challengers at archived prices.

Fixed candidates only; previously inspected data is exploratory. This module has
no production import path, database writes, provider requests, or promotion.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

from sportsbet.quant import current_history_replay as replay
from sportsbet.quant import edge_search_stress as search

WINDOWS = ('history40', 'recent10', 'half_life8', 'half_life16')
CANDIDATES = tuple(name+suffix for name in WINDOWS for suffix in ('', '_market80'))
PROTOCOL = {'version': 'priced-recent-form-v1', 'candidates': CANDIDATES,
            'training_minimum_games': 5, 'training_minimum_player_games': 50,
            'selection_loss': 'equal game then player then market Brier',
            'high_confidence_cutoff': .75, 'minimum_expected_return': .02,
            'scope': 'Previously inspected archive; exploratory, no promotion'}


def predictions(sample, line, market):
    if len(sample) < 20 or not 0 < market < 1:
        raise ValueError('Require twenty as-of observations and a paired market probability')
    # History.sample returns newest first. Missing observations stay missing.
    values = [value for _, value, _ in sample]
    result = {}
    for name in WINDOWS:
        recent = values[:10] if name == 'recent10' else values
        half = 8 if name == 'half_life8' else 16 if name == 'half_life16' else None
        weights = [2**(-i/half) if half else 1. for i in range(len(recent))]
        mass = sum(weights)
        p = round((sum(w*(value > line) for w, value in zip(weights, recent))+.5)/(mass+1), 6)
        result[name] = p
        # Same fixed prior strength as the existing paper; weighted evidence mass
        # (not total historical row count) determines shrinkage for recency models.
        result[name+'_market80'] = (mass*p+80*market)/(mass+80)
    return result


def training_rows(history, target):
    return [x for x in history if x['y'] is not None and x['observed'] is not None
            and x['observed'] < target['entry'] and x['entry'] < target['entry']
            and x['start'] < target['entry'] and x['unit'][0] != target['unit'][0]]


def choose(history, target):
    rows = training_rows(history, target)
    games = {x['unit'][0] for x in rows}
    pairs = {(x['unit'][0], x['unit'][1]) for x in rows}
    counts = {'games': len(games), 'player_games': len(pairs), 'units': len(rows)}
    if len(games) < PROTOCOL['training_minimum_games'] or len(pairs) < PROTOCOL['training_minimum_player_games']:
        return None, counts
    players = defaultdict(set)
    markets = Counter(x['unit'][:2] for x in rows)
    for x in rows:
        players[x['unit'][0]].add(x['unit'][1])
    losses = {name: sum((x['candidate_p'][name]-x['y'])**2 /
                       (len(players[x['unit'][0]])*markets[x['unit'][:2]]) for x in rows)/len(games)
              for name in CANDIDATES}
    # Stable predeclared tie order, never target outcome or final full-archive ROI.
    selected = min(CANDIDATES, key=lambda name: (losses[name], CANDIDATES.index(name)))
    return selected, dict(counts, brier_losses=losses)


def accuracy(selected):
    settled = [c for c in selected if search.result(c) is not None]
    games = defaultdict(list)
    for c in settled:
        games[c['x']['unit'][0]].append(int(search.result(c) > 0))
    wins = sum(sum(values) for values in games.values())
    return {'selected': len(selected), 'settled': len(settled), 'pending': len(selected)-len(settled),
            'games': len(games), 'wins': wins, 'win_rate': wins/len(settled) if settled else None,
            'win_rate_game_cluster_95': search.frozen.cluster_interval(games),
            'mean_predicted_settled': mean(c['probability'] for c in settled) if settled else None,
            'mean_price_break_even_settled': mean(1/(1+c['profit']) for c in settled) if settled else None}


def summarize(observed):
    selected = search.select_model(observed)
    bins = {}
    for lower, upper in ((0,.55),(.55,.65),(.65,.75),(.75,.85),(.85,1.01)):
        bins[f'{lower:.2f}-{min(1,upper):.2f}'] = accuracy([c for c in selected if lower <= c['probability'] < upper])
    high = [c for c in selected if c['probability'] >= .75]
    all_units = search.frozen.earliest_units(observed)
    return {'performance': search.metrics(selected), 'accuracy': accuracy(selected),
            'high_confidence_75': dict(accuracy(high), performance=search.metrics(high)),
            'calibration_bins': bins,
            'all_earliest_units_calibration': search.frozen.score(all_units, lambda x: x['p'])}


def run(rows, snapshot, sport):
    original, excluded = search.frozen.observations(rows, sport, 'empirical-jeffreys-v4')
    history = replay.History(snapshot)
    samples = {}
    observed = []
    rejected = Counter()
    for x in original:
        day = x['start'].astimezone(ZoneInfo('America/New_York')).date()
        key = (x['row']['player_id'], x['row']['prop_type'], day, x['entry'])
        if key not in samples:
            samples[key] = history.sample(sport, *key[:2], day, x['entry'])[0]
        sample = samples[key]
        if len(sample) < 20:
            rejected['insufficient_as_of_history'] += 1
            continue
        observed.append(dict(x, candidate_p=predictions(sample, float(x['row']['line']), x['q'])))
    reports = {}
    for name in CANDIDATES:
        reports[name] = summarize([dict(x, p=x['candidate_p'][name]) for x in observed])
    units = search.frozen.earliest_units(observed)
    adaptive = []
    decisions = []
    choices = {}
    for x in observed:
        key = (x['entry'], x['unit'][0])
        if key not in choices:
            choices[key] = choose(units, x)
        name, training = choices[key]
        decisions.append({'source_prediction_id': x['row']['prediction_id'],
                          'decision_at': x['entry'].isoformat(), 'selected_candidate': name,
                          'training': training})
        if name is not None:
            adaptive.append(dict(x, p=x['candidate_p'][name]))
    reports['chronological_selector'] = summarize(adaptive)
    # Compare static candidates on exactly the same post-warmup quote universe.
    common = {x['row']['prediction_id'] for x in adaptive}
    comparable = [x for x in observed if x['row']['prediction_id'] in common]
    comparable_units = search.frozen.earliest_units(comparable)
    same_window = {name: search.frozen.score(comparable_units, lambda x, name=name: x['candidate_p'][name])
                   for name in CANDIDATES}
    return {'sport': sport, 'archive_eligible_quotes': len(original), 'replayed_quotes': len(observed),
            'archive_exclusions': excluded, 'replay_exclusions': dict(rejected), 'policies': reports,
            'post_warmup_same_units_calibration': same_window, 'selector_decisions': decisions,
            'promote': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger-path', type=Path, required=True)
    parser.add_argument('--history-path', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = search.frozen.OfflineLedger(args.ledger_path).predictions()
    snapshot = json.loads(args.history_path.read_text(encoding='utf-8'))
    report = {'protocol': PROTOCOL, 'observed_at': datetime.now(timezone.utc).isoformat(),
              'inputs': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.ledger_path,args.history_path)},
              'implementations': {Path(m.__file__).name: hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
                                  for m in (replay,search,search.frozen)},
              'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'limitations': ['Historical exploratory comparisons across multiple candidates; no untouched holdout.',
                  'A 75% prediction threshold is not a promise of 75% observed accuracy.',
                  'Intervals are unadjusted exploratory game-cluster intervals; small cohorts cannot validate a claim.',
                  'Chronological selection uses only earlier authenticated labels and excludes the target game.',
                  'High-confidence subsets retain the same first selection per player/game; they do not search later quotes for winners.',
                  'Current retained history cannot restore overwritten versions or past effective-view conflicts.',
                  'Recency is based on observed stat-category games; missing weeks or participation are not invented.',
                  'NFL passing/rushing receive the conservative source-time restriction documented by current-history replay.',
                  'Production roster, uncertainty, portfolio and availability gates are not replayed.',
                  'NBA has no retained quote cohort in this archive.'], 'reports': {}}
    for sport in ('nfl','cfb'):
        report['reports'][sport] = run(rows,snapshot,sport)
        print(sport+' recent-form replay complete',flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')


if __name__ == '__main__':
    main()
