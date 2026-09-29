"""Offline counterfactual replay of current history rules at archived decision times.

Never rewrites forecasts or promotes a strategy. Retained source rows are not a
complete temporal database: overwritten versions and past view conflicts cannot
be reconstructed. Keep generated reports private.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from sportsbet.model_contract import CFB_MODEL_VERSION, NFL_MODEL_VERSION
from sportsbet.prop.probability import empirical_outcome_probabilities
from sportsbet.quant import edge_search_stress as search
from sportsbet.quant import edge_matched_controls as controls

COLUMNS = {'pass_yds': 'passing_yards', 'rush_yds': 'rushing_yards',
           'rec_yds': 'receiving_yards', 'receptions': 'receptions'}
PROTOCOL = {'version': 'current-history-replay-v1', 'last_n_games': 40,
            'minimum_sample': 20, 'minimum_expected_return': .02,
            'scope': 'Exploratory counterfactual core-model replay; never a production qualification replay'}


def stamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed if parsed.utcoffset() is not None else None
    except ValueError:
        return None


def digest(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


class History:
    def __init__(self, snapshot):
        self.players = {}
        for name, field in [('nfl_base', 'player_id'), ('nfl_receiving', 'player_id'), ('cfb', 'athlete_id')]:
            grouped = defaultdict(list)
            for row in snapshot[name]:
                grouped[str(row[field])].append(row)
            self.players[name] = grouped
        self.schedule = defaultdict(list)
        for game in snapshot['nfl_games']:
            for team in (game['home_team'], game['away_team']):
                self.schedule[game['season'], game['week'], team].append(date.fromisoformat(game['game_date']))
        self.receipts = defaultdict(list)
        for athlete, game, inserted, sha in snapshot['cfb_supplement_receipts']:
            self.receipts[str(athlete), str(game), sha].append(stamp(inserted))

    def sample(self, sport, player, prop, cutoff, decision):
        if sport not in ('nfl', 'cfb') or prop not in COLUMNS or decision.utcoffset() is None:
            raise ValueError('Unsupported replay context')
        source = 'cfb' if sport == 'cfb' else 'nfl_receiving' if prop in ('rec_yds', 'receptions') else 'nfl_base'
        season = cutoff.year if cutoff.month >= 9 else cutoff.year-1
        exclusions = Counter()
        eligible = []
        for row in self.players[source].get(str(player), []):
            value = row.get(COLUMNS[prop])
            if row['season'] < season-2:
                exclusions['older_season'] += 1
                continue
            if type(value) not in (int, float) or not math.isfinite(value):
                exclusions['missing_stat'] += 1
                continue
            if sport == 'cfb':
                before = date.fromisoformat(row['game_date']) < cutoff
                key = (row['game_date'], str(row['game_id']))
            else:
                before = any(day < cutoff for day in self.schedule[row['season'], row['week'], row.get('team')])
                key = (row['season'], row['week'])
            if not before:
                exclusions['not_before_game_cutoff_or_missing_schedule'] += 1
                continue
            observed = stamp(row.get('source_observed_at'))
            if observed is None or observed > decision:
                exclusions['source_unavailable_at_decision'] += 1
                continue
            if not row.get('source_provider') or not all(digest(row.get(field)) for field in ('source_sha256', 'source_record_sha256')):
                exclusions['missing_source_commitment'] += 1
                continue
            if row.get('supplement_manifest') or (sport == 'nfl' and row.get('supplement_inserted_at') is not None):
                receipts = (self.receipts[str(player), str(row['game_id']), row['source_sha256']]
                            if sport == 'cfb' else [stamp(row.get('supplement_inserted_at'))])
                if not any(receipt is not None and receipt <= decision for receipt in receipts):
                    exclusions['supplement_unavailable_at_decision'] += 1
                    continue
            eligible.append((key, value, row['source_record_sha256']))
        # A duplicate history key cannot silently contribute twice to sample size.
        if len({key for key, _, _ in eligible}) != len(eligible):
            return [], dict(exclusions, duplicate_history_key=1)
        eligible.sort(key=lambda item: item[0], reverse=True)
        exclusions['outside_last_40'] += max(0, len(eligible)-40)
        return eligible[:40], dict(exclusions)


def estimate(sample, line):
    values = [value for _, value, _ in sample]
    if not values:
        return None
    successes = sum(value > line for value in values)
    pushes = sum(value == line for value in values)
    if pushes == len(values):
        return None
    p, push, interval = empirical_outcome_probabilities(successes, pushes, len(values))
    return {'n': len(values), 'successes': successes, 'pushes': pushes,
            'p': float(p.quantize(Decimal('0.000001'))), 'push_probability': float(push),
            'interval': [float(v.quantize(Decimal('0.000001'))) for v in interval],
            'mean': round(sum(values)/len(values), 2),
            'history_sha256': hashlib.sha256(json.dumps(sample, sort_keys=True).encode()).hexdigest()}


def replay(rows, snapshot, sport, source_version='empirical-jeffreys-v4'):
    observed, archive_excluded = search.frozen.observations(rows, sport, source_version)
    history = History(snapshot)
    adapted = []
    evidence = []
    rejected = Counter()
    samples = {}
    for x in observed:
        day = x['start'].astimezone(ZoneInfo('America/New_York')).date()
        key = (x['row']['player_id'], x['row']['prop_type'], day, x['entry'])
        if key not in samples:
            samples[key] = history.sample(sport, *key[:2], day, x['entry'])
        sample, reasons = samples[key]
        calculated = estimate(sample, float(x['row']['line']))
        evidence.append({'source_prediction_id': x['row']['prediction_id'],
                         'decision_at': x['entry'].isoformat(), 'game_date_cutoff': day.isoformat(),
                         'estimate': calculated, 'history_exclusions': reasons})
        if calculated is None or calculated['n'] < 20:
            rejected['insufficient_as_of_history'] += 1
            continue
        if calculated['push_probability'] != 0:
            rejected['unsupported_push_mass'] += 1
            continue
        adapted.append(dict(x, p=calculated['p'], n=calculated['n']))
    prices = controls.price_observations(rows, sport, source_version)
    policies = {}
    for name, prior in [('raw_model', False), ('market_prior80', True)]:
        selected = search.select_model(adapted, prior)
        policies[name] = {'performance': search.metrics(selected),
                          'matched_controls': controls.compare(selected, prices)}
    return {'sport': sport, 'target_model_version': {'nfl': NFL_MODEL_VERSION, 'cfb': CFB_MODEL_VERSION}[sport],
            'source_model_version': source_version, 'archive_eligible_quotes': len(observed),
            'replayed_quotes': len(adapted), 'archive_exclusions': archive_excluded,
            'replay_exclusions': dict(rejected), 'policies': policies, 'evidence': evidence,
            'promote': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger-path', type=Path, required=True)
    parser.add_argument('--history-path', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = search.frozen.OfflineLedger(args.ledger_path).predictions()
    snapshot = json.loads(args.history_path.read_text(encoding='utf-8'))
    dependencies = [Path(__file__), Path(search.__file__), Path(controls.__file__),
                    Path(search.frozen.__file__), Path('src/sportsbet/prop/probability.py'),
                    Path('src/sportsbet/prop/query_builder.py'), Path('src/sportsbet/model_contract.py')]
    report = {'protocol': PROTOCOL, 'observed_at': datetime.now(timezone.utc).isoformat(),
              'inputs': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.ledger_path, args.history_path)},
              'implementations': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in dependencies},
              'limitations': [
                  'Counterfactual current core probabilities, not retained production forecasts or executed returns.',
                  'Archive was already inspected; selection and confidence intervals are exploratory.',
                  'Only archived half-lines with original sample >=20 and verified prices/outcomes are eligible.',
                  'Current retained history cannot recover overwritten versions or prior effective-view conflicts.',
                  'All sports require source receipts by decision time; NFL passing/rushing SQL lacks this extra conservative restriction.',
                  'Later inserted supplements are excluded, even when their source describes earlier games.',
                  'Availability, uncertainty, exposure and production admission gates are not replayed.',
                  'NBA has no quotes in this archive and is not evaluated.'],
              'reports': {sport: replay(rows, snapshot, sport) for sport in ('nfl', 'cfb')}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    for sport, result in report['reports'].items():
        print(sport, 'replay complete:', result['replayed_quotes'], 'quotes; report saved privately')


if __name__ == '__main__':
    main()
