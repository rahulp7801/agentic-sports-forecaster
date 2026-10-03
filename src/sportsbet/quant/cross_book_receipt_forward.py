"""Private forward price experiment using committed alternate-book receipts."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import mean, median

from sportsbet.ledger import utc_timestamp
from sportsbet.quant import cross_book_forward as old, market_challengers as challenger
from sportsbet.quant import cross_book_quote_receipt as quote_receipt
from sportsbet.quant.cross_book_quote_receipt import VERSION, verified_references
from sportsbet.quant.audit_storage import audit_database_url


PROTOCOL = dict(version='cross-book-receipt-forward-v2',
    captured_after='2026-10-03T00:00:00+00:00',
    receipt_version=VERSION, maximum_quote_age_seconds=300,
    minimum_expected_return=.02, minimum_paired_games=50,
    minimum_decided_selections=100, minimum_selection_games=30,
    automatic_promotion=False)
CAPTURE_SHA256 = 'df7e653a6b9c43533a0ede50c4d107275a91725a176926e8bb867d364164044d'


def evaluate(rows, sport, *, now=None):
    """Select one earliest qualifying offer per player/game without outcomes."""
    if sport not in old.PROTOCOL['model_versions']:
        raise ValueError('Unsupported sport')
    if old.source_digests() != old.FROZEN_DIGESTS:
        raise ValueError('Frozen v1 dependencies changed; new protocol required')
    if hashlib.sha256(Path(quote_receipt.__file__).read_text(encoding='utf-8').encode()).hexdigest() != CAPTURE_SHA256:
        raise ValueError('Frozen v2 quote capture changed; new protocol required')
    now = now or datetime.now(timezone.utc)
    cutoff = utc_timestamp(PROTOCOL['captured_after'])
    scoped = []
    for row in rows:
        if row.get('sport') != sport or row.get('model_version') != old.PROTOCOL['model_versions'][sport]:
            continue
        entered = utc_timestamp(row['captured_at'])
        if entered < cutoff:
            continue
        if entered > now:
            raise ValueError('Future capture cannot enter this audit')
        if (row.get('recommendation_policy_version') != old.PROTOCOL['recommendation_policy_version']
                or row.get('history_policy_version') != old.PROTOCOL['history_policies'].get(sport, row.get('history_policy_version'))):
            raise ValueError('Changed or missing model policy')
        if (utc_timestamp(row['quote_time']) < cutoff
                or utc_timestamp(row['model_generated_at']) < cutoff):
            continue
        scoped.append(row)
    observed, excluded = challenger.observations(scoped, sport, old.PROTOCOL['model_versions'][sport])
    proposals = []
    coverage = Counter()
    batches = defaultdict(list)
    for x in observed:
        batches[(x['unit'][0], x['unit'][1],
            x['row']['quote_source_sha256'])].append(x)
    for items in batches.values():
        decision = max(x['entry'] for x in items)
        for x in items:
            row = x['row']
            if (decision >= x['start'] or not 0 <= (decision-x['quote']).total_seconds()
                    <= PROTOCOL['maximum_quote_age_seconds']):
                coverage['stale_offer'] += 1
                continue
            references = verified_references(row, decision_at=decision)
            if references is None:
                coverage['missing_or_invalid_receipt'] += 1
                continue
            if not references:
                coverage['no_fresh_other_book_pair'] += 1
                continue
            coverage['comparable_offers'] += 1
            over_probability = median(references.values())
            probability = over_probability if row['direction'] == 'over' else 1-over_probability
            odds = row['american_odds']
            profit = odds/100 if odds > 0 else 100/-odds
            ev = probability*(profit+1)-1
            if ev >= PROTOCOL['minimum_expected_return']:
                proposals.append(dict(x=x, decision=decision, probability=probability,
                    ev=ev, profit=profit, reference_books=sorted(references)))
    proposals.sort(key=lambda c:(c['decision'], -c['ev'], c['x']['row']['prediction_id']))
    selected = []
    seen = set()
    for candidate in proposals:
        key = candidate['x']['unit'][:2]
        if key not in seen:
            seen.add(key)
            selected.append(candidate)
    scores = []
    returns = defaultdict(list)
    manifest = []
    for c in selected:
        x = c['x']
        row = x['row']
        over = row['direction'] == 'over'
        outcome = x['y'] if x['observed'] is None or x['observed'] <= now else None
        scores.append(dict(x, y=outcome,
            p=c['probability'] if over else 1-c['probability']))
        won = None if outcome is None else bool(outcome) == over
        if won is not None:
            returns[x['unit'][0]].append(c['profit'] if won else -1.)
        manifest.append(dict(prediction_id=row['prediction_id'],game_id=x['unit'][0],
            player_id=x['unit'][1],prop_type=x['unit'][2],line=x['unit'][3],
            decision_at=c['decision'].isoformat(),direction=row['direction'],
            sportsbook=row['sportsbook'],american_odds=row['american_odds'],
            reference_probability=c['probability'],estimated_return=c['ev'],
            reference_books=c['reference_books'],
            quote_source_sha256=row['quote_source_sha256'],verified_outcome=won))
    values = [value for group in returns.values() for value in group]
    interval = challenger.cluster_interval(returns)
    scored = challenger.score(scores, lambda x:x['p'])
    adequate = (scored['games'] >= PROTOCOL['minimum_paired_games']
        and len(values) >= PROTOCOL['minimum_decided_selections']
        and len(returns) >= PROTOCOL['minimum_selection_games'])
    supported = bool(adequate and interval and interval[0] > 0
        and scored['game_cluster_95'] and scored['game_cluster_95'][1] < 0)
    return dict(protocol=PROTOCOL,old_dependency_sha256=old.source_digests(),
        capture_sha256=CAPTURE_SHA256,
        protocol_sha256=hashlib.sha256(json.dumps(PROTOCOL,sort_keys=True).encode()).hexdigest(),
        evaluator_sha256=hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest(),
        observed_at=now.isoformat(),sport=sport,promote=False,
        status='awaiting_start' if now < cutoff else 'insufficient_evidence' if not adequate
            else 'review_required' if supported else 'edge_not_demonstrated',
        recorded_rows=len(scoped),eligible_rows=len(observed),excluded=excluded,
        coverage=dict(coverage),selected=len(selected),decided=len(values),
        pending=len(selected)-len(values),settled_games=len(returns),
        wins=sum(v>0 for v in values),flat_stake_roi=mean(values) if values else None,
        roi_game_cluster_95=interval,probability_scores=scored,selections=manifest,
        scope='Future source-backed hypothetical prices; no bets or production picks.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger-path',type=Path)
    parser.add_argument('--database-env')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--sport',choices=['nba','nfl','cfb','all'],default='all')
    args = parser.parse_args()
    if args.ledger_path and args.database_env:
        parser.error('Choose a local ledger or a database environment')
    if args.ledger_path:
        rows = challenger.OfflineLedger(args.ledger_path).predictions()
    else:
        from dotenv import load_dotenv
        load_dotenv()
        ledger = old.ProspectiveLedger(database_url=audit_database_url(args.database_env))
        with ledger.snapshot():
            rows = ledger.predictions()
    now = datetime.now(timezone.utc)
    sports = list(old.PROTOCOL['model_versions']) if args.sport == 'all' else [args.sport]
    reports = {sport:evaluate(rows,sport,now=now) for sport in sports}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(reports,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({sport:report['status'] for sport,report in reports.items()}))


if __name__ == '__main__':
    main()
