"""Private context diagnostics for existing paper picks; no new selection policy.

The selections were recorded prospectively. These diagnostic subgroups are
exploratory and are not a separately preregistered 75% performance experiment.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import platform
from statistics import mean
import sys

from sportsbet.ledger import utc_timestamp
from sportsbet.quant import model_selection_paper as paper
from sportsbet.quant import nfl_recent_role_shadow as role
from sportsbet.quant import edge_search_stress as search
from sportsbet.quant.audit_storage import audit_database_url

PROTOCOL = {'version': 'individual-pick-context-audit-v1', 'sport': 'nfl',
    'source_policy': 'raw_model', 'target_probability': .75, 'recent_games': 10,
    'maximum_recent_gap_days': 30, 'minimum_current_games': 2,
    'rules': ['original_75', 'recent_agreement_75', 'recent_and_current_role_75'],
    'scope': 'Exploratory context subgroups of immutable prospective paper selections; no replacement picks',
    'automatic_promotion': False}


def require_matching_runtime():
    # Frozen v2 receipts include gzip bytes. Python 3.12 on Windows encodes a
    # different gzip OS byte than the original Linux worker; never repair a receipt.
    if (platform.system() != 'Linux' or platform.python_implementation() != 'CPython' or sys.version_info[:2] != (3, 12)
            or gzip.compress(b'runtime-check', compresslevel=6, mtime=0)[9] != 3):
        raise ValueError('Frozen role replay requires Linux CPython 3.12')


def context(row, paper_recorded_at):
    record = row.get('role_history_shadow')
    if not isinstance(record, dict) or record.get('model_version') != role.VERSION:
        return {'available': False, 'reason': 'missing_current_role_receipt'}
    if record.get('status') != 'predicted':
        reason = record.get('reason')
        return {'available': False, 'reason': reason if isinstance(reason, str) and reason in role.REASONS else 'invalid_role_receipt'}
    probability = role.verified_recorded_shadow_probability(row)
    if probability is None:
        return {'available': False, 'reason': 'invalid_role_receipt'}
    if utc_timestamp(row['role_history_shadow_recorded_at']) > paper_recorded_at:
        return {'available': False, 'reason': 'context_recorded_after_selection'}
    rows, _ = role.validated_rows(json.dumps(record['inputs'], sort_keys=True, separators=(',', ':')))
    latest = sorted(rows, key=lambda item: (item['day'], item['season'], item['week']), reverse=True)
    gap = (date.fromisoformat(row['game_date']) - date.fromisoformat(latest[0]['day'])).days
    stat = role.MARKETS['nfl'][row['prop_type']]
    over = (sum(item[stat] > float(row['line']) for item in latest[:10]) + .5) / 11
    recent = over if row['direction'] == 'over' else 1 - over
    team = {'LAR': 'LA', 'WSH': 'WAS'}.get(row['availability']['team'], row['availability']['team'])
    return {'available': True, 'recent_probability': recent, 'role_probability': probability,
        'latest_game_gap_days': gap, 'current_role_games': record['counts']['current_role_games'],
        'older_games': record['counts']['older_games'], 'latest_team_matches': latest[0]['team'] == team,
        'fresh': 0 <= gap <= PROTOCOL['maximum_recent_gap_days']}


def rules(probability, evidence):
    original = probability >= PROTOCOL['target_probability']
    recent = bool(original and evidence['available'] and evidence['fresh']
                  and evidence['recent_probability'] >= PROTOCOL['target_probability'])
    current = bool(recent and evidence['latest_team_matches']
                   and evidence['current_role_games'] >= PROTOCOL['minimum_current_games']
                   and evidence['older_games'] > 0
                   and evidence['role_probability'] >= PROTOCOL['target_probability'])
    return dict(original_75=original, recent_agreement_75=recent, recent_and_current_role_75=current)


def summarize(entries, now):
    decided = [entry for entry in entries if type(entry['outcome']) is bool]
    games = defaultdict(list); returns = defaultdict(list)
    for entry in decided:
        games[entry['game_id']].append(int(entry['outcome']))
        returns[entry['game_id']].append(search.profit(entry['american_odds']) if entry['outcome'] else -1.)
    wins = sum(entry['outcome'] for entry in decided)
    return dict(selected=len(entries), upcoming=sum(utc_timestamp(e['game_start_time']) > now for e in entries),
        pending=len(entries)-len(decided), decided=len(decided), wins=wins, settled_games=len(games),
        win_rate=wins/len(decided) if decided else None,
        win_rate_game_cluster_95=search.frozen.cluster_interval(games),
        flat_stake_roi=mean(v for values in returns.values() for v in values) if decided else None,
        roi_game_cluster_95=search.frozen.cluster_interval(returns),
        mean_recorded_probability=mean(e['probability'] for e in decided) if decided else None,
        mean_market_probability=mean(e['market_probability'] for e in decided) if decided else None)


def audit(receipts, predictions, now):
    require_matching_runtime()
    ids = [row['prediction_id'] for row in predictions]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate prediction identity')
    # Preserve the existing selector, price proofs, deadlines and source/settlement
    # authentication. Do not select a later quote when the original lacks context.
    verified = paper.audit_receipts(receipts, predictions, 'nfl', 'raw_model', now)
    result = dict(protocol=PROTOCOL, observed_at=now.isoformat(), source_audit=verified,
        runtime=dict(system=platform.system(), python=platform.python_version()),
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        role_implementation_sha256=role.implementation_sha256(), promote=False,
        target_verified=False, status='exploratory_only', selections=[], groups={})
    if verified['invalid_receipts']:
        result['status'] = 'invalid_source_evidence'
        return result
    by_id = {row['prediction_id']: row for row in predictions}
    details = []; missing = Counter(); selected_groups = {name: [] for name in PROTOCOL['rules']}
    for receipt in receipts:
        if receipt['sport'] != 'nfl' or receipt['protocol'] != paper.PROTOCOL['policies']['raw_model']:
            continue
        selection = json.loads(receipt['payload'])['selection']; row = by_id[receipt['prediction_id']]
        evidence = context(row, utc_timestamp(str(receipt['recorded_at'])))
        if not evidence['available']:
            missing[evidence['reason']] += 1
        outcome = search.frozen.audit._verified_outcome(row)
        if (type(outcome) is not bool or utc_timestamp(row['outcome_observed_at']) > now
                or utc_timestamp(row['game_start_time']) > now):
            outcome = None
        chosen = rules(selection['probability'], evidence)
        detail = dict(selection, context=evidence, rules=chosen, outcome=outcome)
        details.append(detail)
        for name, enabled in chosen.items():
            if enabled:
                selected_groups[name].append(detail)
    result.update(selections=details, coverage=dict(original_selections=len(details),
        current_context_available=sum(d['context']['available'] for d in details),
        unavailable_reasons=dict(missing)),
        groups={name: summarize(entries, now) for name, entries in selected_groups.items()},
        limitations=['These are private hypothetical paper picks, not accepted dashboard picks or bets.',
            'Context subgroups are exploratory; no 75% accuracy or profitability claim is authorized.',
            'Missing original context stays missing; later quotes and outcomes never replace selections.',
            'Intervals are descriptive, game-clustered and unadjusted for subgroup search.',
            'NFL receiving context only; NBA and CFB require separate source-backed candidates.'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require_matching_runtime()  # Fail before any database access on an incompatible host.
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
        ledger.ids = sorted({r['prediction_id'] for receipt in receipts for r in json.loads(receipt['payload'])['evidence']})
        predictions = ledger.predictions()
    report = audit(receipts, predictions, datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print('Private individual-pick context audit completed')


if __name__ == '__main__':
    main()
