"""Frozen cross-book forward research; reads existing records, never places bets."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import mean

from sportsbet import ledger as ledger_module, model_contract
from sportsbet.ingestion import prop_odds
from sportsbet.ledger import utc_timestamp
from sportsbet.quant import market_challengers as challenger
from sportsbet.quant import market_baseline, priced_market_audit
from sportsbet.quant.audit_storage import ReadOnlyLedger, audit_database_url

PROTOCOL = {
    'version': 'cross-book-forward-v1',
    'captured_after': '2026-09-30T00:00:00+00:00',
    'model_versions': {
        'nfl': 'empirical-jeffreys-v4-nfl-history-v1',
        'cfb': 'empirical-jeffreys-v4-cfb-history-v1',
        'nba': 'empirical-jeffreys-v4',
    },
    'history_policies': {'nfl':'nfl-explicit-receiving-v1','cfb':'cfb-explicit-receiving-v1'},
    'recommendation_policy_version': 'confidence-floor-v2',
    'minimum_paired_games': 50,
    'minimum_decided_selections': 100,
    'minimum_selection_games': 30,
    'automatic_promotion': False,
}
# Filled at implementation freeze. A changed dependency requires a new protocol.
FROZEN_DIGESTS = {'sportsbet.quant.market_challengers': 'bb99ceb40450f0fcbebeb3730e75211954628d1ec8cf410d167f1a3bbc84f4df', 'sportsbet.quant.market_baseline': 'bffd86272a1eac303acb57dbd0b246355b8d2d5b2ab4c39945d5e8d5c3af9404', 'sportsbet.quant.priced_market_audit': '6925b66315c7daeab86f0c1cab57c02c7abda9f237f6a80242dba94d8419a5be', 'sportsbet.ledger': 'e33611de7f85c376b2967f3d1f1bf4a02e80ce093d85c7a1182d29b8799fe2b1', 'sportsbet.model_contract': '96cac511ca3ae555e953985167a18639ef06148947c82a00d8b6c4bc241f4f29', 'sportsbet.ingestion.prop_odds': 'e5ca0fd05e4bfacbff670c925016526b24ae6f9cf8ed0e1d43762c670cbf5ad3'}


def source_digests():
    return {module.__name__:hashlib.sha256(Path(module.__file__).read_text(encoding='utf-8').encode('utf-8')).hexdigest()
        for module in (challenger,market_baseline,priced_market_audit,ledger_module,model_contract,prop_odds)}


def evaluate(rows, sport, *, now=None):
    if sport not in PROTOCOL['model_versions']:
        raise ValueError('Unsupported sport')
    if source_digests()!=FROZEN_DIGESTS:
        raise ValueError('Frozen evaluator dependencies changed; new protocol required')
    now=now or datetime.now(timezone.utc)
    cutoff=utc_timestamp(PROTOCOL['captured_after'])
    version=PROTOCOL['model_versions'][sport]
    scoped=[]
    for row in rows:
        if row.get('sport')!=sport or row.get('model_version')!=version:
            continue
        entered=utc_timestamp(row['captured_at'])
        if entered<cutoff:
            continue
        if entered>now:
            raise ValueError('Future capture cannot enter this audit')
        if row.get('recommendation_policy_version')!=PROTOCOL['recommendation_policy_version']:
            raise ValueError('Changed or missing recommendation policy')
        policy=PROTOCOL['history_policies'].get(sport)
        if policy and row.get('history_policy_version')!=policy:
            raise ValueError('Changed or missing history policy')
        if utc_timestamp(row['quote_time'])<cutoff or utc_timestamp(row['model_generated_at'])<cutoff:
            continue
        scoped.append(row)
    observed,excluded=challenger.observations(scoped,sport,version)
    # Future settlement timestamps cannot enter even if the caller replays as-of.
    for x in observed:
        if x['observed'] is not None and x['observed']>now:
            x['y']=None;x['observed']=None
    selected,coverage=challenger.cross_book_candidates(observed)
    returns=defaultdict(list);scored=[];manifest=[]
    for candidate in selected:
        x=candidate['x'];row=x['row'];over=row['direction']=='over'
        p=candidate['probability'];scored.append(dict(x,p=p if over else 1-p))
        won=None if x['y'] is None else bool(x['y'])==over
        if won is not None:
            returns[x['unit'][0]].append(candidate['profit'] if won else -1.)
        manifest.append(dict(prediction_id=row['prediction_id'],game_id=x['unit'][0],
            player_id=x['unit'][1],prop_type=x['unit'][2],line=x['unit'][3],
            decision_at=candidate['decision'].isoformat(),direction=row['direction'],
            sportsbook=row['sportsbook'],american_odds=row['american_odds'],
            reference_probability=p,estimated_return=candidate['ev'],
            reference_prediction_ids=candidate['reference_prediction_ids'],
            quote_source_sha256=row['quote_source_sha256'],verified_outcome=won))
    scores=challenger.score(scored,lambda x:x['p'])
    values=[value for group in returns.values() for value in group]
    interval=challenger.cluster_interval(returns)
    ready=(scores['games']>=PROTOCOL['minimum_paired_games']
        and len(values)>=PROTOCOL['minimum_decided_selections']
        and len(returns)>=PROTOCOL['minimum_selection_games'])
    supported=bool(ready and interval and interval[0]>0
        and scores['game_cluster_95'] and scores['game_cluster_95'][1]<0)
    return dict(protocol=PROTOCOL,selection_protocol=challenger.PROTOCOL,
        protocol_sha256=hashlib.sha256(json.dumps(PROTOCOL,sort_keys=True).encode()).hexdigest(),
        evaluator_sha256=source_digests(),runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        observed_at=now.isoformat(),sport=sport,promote=False,
        status=('awaiting_start' if now<cutoff else 'insufficient_evidence' if not ready
            else 'review_required' if supported else 'edge_not_demonstrated'),
        recorded_rows=len(scoped),eligible_rows=len(observed),excluded=excluded,
        coverage=coverage,selected=len(selected),decided=len(values),
        pending=len(selected)-len(values),settled_games=len(returns),
        wins=sum(v>0 for v in values),flat_stake_roi=mean(values) if values else None,
        roi_game_cluster_95=interval,probability_scores=scores,selections=manifest,
        scope='Future source-backed hypothetical price selections; no executed returns or production picks.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger-path',type=Path)
    parser.add_argument('--database-env')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--sport',choices=['nba','nfl','cfb','all'],default='all')
    args=parser.parse_args()
    if args.ledger_path and args.database_env:
        parser.error('Choose a local ledger or a database environment, not both')
    if args.ledger_path:
        rows=challenger.OfflineLedger(args.ledger_path).predictions()
    else:
        from dotenv import load_dotenv
        load_dotenv()
        ledger=ReadOnlyLedger(database_url=audit_database_url(args.database_env))
        with ledger.snapshot():
            rows=ledger.predictions()
    now=datetime.now(timezone.utc)
    sports=list(PROTOCOL['model_versions']) if args.sport=='all' else [args.sport]
    reports={sport:evaluate(rows,sport,now=now) for sport in sports}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(reports,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({sport:report['status'] for sport,report in reports.items()}))


if __name__=='__main__':main()
