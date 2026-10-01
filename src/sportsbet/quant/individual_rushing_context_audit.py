"""Read-only, as-of rushing-history diagnostics for original NFL paper picks.

This reconstruction has no original rushing-input receipt. It cannot certify a
new probability, a current role, or an improvement in selection accuracy.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

from sportsbet.ingestion.provenance import stat_row_sha256
from sportsbet.ledger import utc_timestamp
from sportsbet.quant import current_history_replay as replay
from sportsbet.quant import individual_pick_accuracy as accuracy
from sportsbet.quant import model_selection_paper as paper
from sportsbet.quant import edge_search_stress as search
from sportsbet.quant.audit_storage import audit_database_url


PROTOCOL = {'version': 'individual-rushing-context-audit-v1', 'sport': 'nfl',
            'market': 'rush_yds', 'source_policy': 'raw_model',
            'target_probability': .75, 'recent_games': 10,
            'scope': 'Descriptive as-of reconstruction of original paper selections',
            'automatic_promotion': False}


def reconstructed_context(row, selection, receipt, snapshot, history):
    """Fail closed unless retained rows reproduce the original baseline exactly."""
    capture = replay.stamp(row.get('captured_at'))
    before = replay.stamp(row.get('history_observed_before'))
    recorded = utc_timestamp(str(receipt['recorded_at']))
    snapshot_at = replay.stamp(snapshot.get('observed_at'))
    if (capture is None or before is None or snapshot_at is None or
            not snapshot_at <= before <= capture <= recorded):
        return {'available': False, 'reason': 'invalid_source_chronology'}
    roster, reason = accuracy.context(row, capture)
    if reason:
        return {'available': False, 'reason': reason}
    day = date.fromisoformat(row['game_date'])
    sample, exclusions = history.sample('nfl', row['player_id'], 'rush_yds', day, before)
    if exclusions.get('duplicate_history_key'):
        return {'available': False, 'reason': 'duplicate_history_key'}
    bound, reason = accuracy.bound_history(sample, snapshot, 'nfl', row['player_id'], 'rush_yds')
    if reason:
        return {'available': False, 'reason': reason}
    for source, _ in bound:
        try:
            if (source['source_provider'] != 'nflverse' or
                    stat_row_sha256('nfl', source) != source['source_record_sha256']):
                return {'available': False, 'reason': 'invalid_source_row_commitment'}
        except (KeyError, TypeError, ValueError):
            return {'available': False, 'reason': 'invalid_source_row_commitment'}
        games = [game for game in snapshot['nfl_games']
                 if (game['season'], game['week']) == (source['season'], source['week'])
                 and source['team'] in (game['home_team'], game['away_team'])]
        if len(games) != 1:
            return {'available': False, 'reason': 'ambiguous_schedule_binding'}
        game = games[0]
        expected = f"{source['season']}_{source['week']:02}_{game['away_team']}_{game['home_team']}"
        created = replay.stamp(game.get('created_at'))
        if (game.get('game_id') != expected or created is None or created > before or
                date.fromisoformat(game['game_date']) >= day):
            return {'available': False, 'reason': 'invalid_schedule_chronology'}
    estimate = replay.estimate(sample, float(selection['line']))
    if (estimate is None or estimate['n'] < 20 or estimate['push_probability'] != 0 or
            estimate['n'] != row.get('model_sample_size') or
            estimate['mean'] != row.get('model_mean_stat') or
            (estimate['p'] if row['direction'] == 'over' else 1-estimate['p']) != selection['probability'] or
            selection['probability'] != row['model_probability']):
        return {'available': False, 'reason': 'baseline_not_reproduced'}
    latest = bound[0][0]
    days = history.schedule[latest['season'], latest['week'], latest.get('team')]
    if len(set(days)) != 1 or latest.get('team') != roster['team']:
        return {'available': False, 'reason': 'latest_game_or_team_unverified'}
    gap = (day-days[0]).days
    if not 0 <= gap <= 30:
        return {'available': False, 'reason': 'stale_or_future_game_history'}
    season = day.year if day.month >= 9 else day.year-1
    current = [r for r, _ in bound if r['season'] == season and r.get('team') == roster['team']]
    older = len(bound)-len(current)
    if len(current) < 2:
        return {'available': False, 'reason': 'insufficient_current_season_games'}
    line = float(selection['line'])
    hit = lambda value: value > line if selection['direction'] == 'over' else value < line
    recent = sample[:PROTOCOL['recent_games']]
    # This is a descriptive Jeffreys fraction, not a validated rush-role model.
    return {'available': True, 'evidence_type': 'reconstructed_stat_only',
            'original_input_receipt': False, 'history_sha256': estimate['history_sha256'],
            'baseline_sample_size': estimate['n'], 'baseline_mean_yards': estimate['mean'],
            'baseline_probability': selection['probability'], 'latest_game_gap_days': gap,
            'recent_games': len(recent), 'recent_hits': sum(hit(v) for _, v, _ in recent),
            'recent_fraction_jeffreys': (sum(hit(v) for _, v, _ in recent)+.5)/(len(recent)+1),
            'current_season_games': len(current), 'older_games': older,
            'current_season_hits': sum(hit(r['rushing_yards']) for r in current),
            'current_season_mean_yards': round(sum(r['rushing_yards'] for r in current)/len(current), 2),
            'current_season_carries': [r.get('carries') for r in current],
            'participation_completeness_verified': False}


def audit(receipts, predictions, snapshot, now):
    if len({r['prediction_id'] for r in predictions}) != len(predictions):
        raise ValueError('Duplicate prediction identity')
    verified = paper.audit_receipts(receipts, predictions, 'nfl', 'raw_model', now)
    result = {'protocol': PROTOCOL, 'source_audit': verified, 'observed_at': now.isoformat(),
              'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'status': 'exploratory_only', 'promote': False, 'target_verified': False,
              'selections': [], 'coverage': {}, 'limitations': [
                  'Original private hypothetical paper picks, not accepted dashboard picks or bets.',
                  'Retained source rows reproduce the baseline but are not an original rushing-input receipt.',
                  'Rushing participation completeness and current-role probability are not verified.',
                  'Pending outcomes do not count as wins; no individual-pick 75% or edge claim.']}
    if verified['invalid_receipts']:
        result['status'] = 'invalid_source_evidence'
        return result
    by_id = {r['prediction_id']: r for r in predictions}
    history = replay.History(snapshot)
    missing = Counter()
    for receipt in receipts:
        if receipt['sport'] != 'nfl' or receipt['protocol'] != paper.PROTOCOL['policies']['raw_model']:
            continue
        selection = json.loads(receipt['payload'])['selection']
        if selection['prop_type'] != 'rush_yds':
            continue
        row = by_id[receipt['prediction_id']]
        context = reconstructed_context(row, selection, receipt, snapshot, history)
        if not context['available']:
            missing[context['reason']] += 1
        outcome = search.frozen.audit._verified_outcome(row)
        if (type(outcome) is not bool or utc_timestamp(row['outcome_observed_at']) > now or
                utc_timestamp(row['game_start_time']) > now):
            outcome = None
        result['selections'].append(dict(selection, context=context, outcome=outcome))
    high = [r for r in result['selections'] if r['probability'] >= PROTOCOL['target_probability']]
    result['coverage'] = {'rushing_selections': len(result['selections']),
                          'high_confidence_original': len(high),
                          'high_confidence_reconstructed': sum(r['context']['available'] for r in high),
                          'high_confidence_decided': sum(type(r['outcome']) is bool for r in high),
                          'unavailable_reasons': dict(missing)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv()
    ledger = paper.storage.PaperLedger(database_url=audit_database_url())
    with ledger.snapshot():
        with ledger.connect() as db:
            raw = db.execute("""SELECT protocol,sport,game_id,player_id,prediction_id,decision_at,
                valid_until,recorded_at,payload,payload_sha256 FROM paper_selections
                WHERE protocol=? AND sport=?""", (paper.PROTOCOL['policies']['raw_model'], 'nfl')).fetchall()
        keys = ('protocol','sport','game_id','player_id','prediction_id','decision_at',
                'valid_until','recorded_at','payload','payload_sha256')
        receipts = [dict(zip(keys, row, strict=True)) for row in raw]
        ledger.ids = sorted({r['prediction_id'] for receipt in receipts
                             for r in json.loads(receipt['payload'])['evidence']})
        predictions = ledger.predictions()
    report = audit(receipts, predictions, json.loads(args.snapshot.read_text(encoding='utf-8')),
                   datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print('Private rushing context audit completed')


if __name__ == '__main__':
    main()
