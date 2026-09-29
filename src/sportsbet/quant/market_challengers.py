"""Offline market challengers. No production selection, collection or promotion.

Historical data has already been inspected. Walk-forward results are exploratory;
only source-verified outcomes observed before each entry can enter a fitted model.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import sqlite3
from statistics import mean, median

from sportsbet.ledger import Ledger, utc_timestamp
from sportsbet.quant import priced_market_audit as audit
from sportsbet.quant.market_baseline import verified_recorded_market_baseline

PROTOCOL = {
    'version': 'offline-market-challengers-v1',
    'market_prior_strength': 80,
    'minimum_training_games': 5,
    'quote_max_age_seconds': 300,
    'cross_book_minimum_expected_return': .02,
    'bootstrap_samples': 10000,
    'bootstrap_seed': 20260929,
    'scope': 'exploratory historical replay; no automatic promotion',
}


def _raw(odds):
    return 100/(odds+100) if odds > 0 else -odds/(-odds+100)


def _unit(row):
    return row['game_id'], row['player_id'], row['prop_type'], row['line']


def observations(rows, sport, version):
    """Only retained half-line forecasts with reproducible same-book baselines."""
    eligible=[];excluded=Counter()
    for row in rows:
        if audit._eligible(row,sport,version) is None:
            if row.get('sport')==sport and row.get('model_version')==version:
                excluded['ineligible_metadata_or_evidence']+=1
            continue
        if not audit.quote_evidence_valid(row) or not audit.settlement_identity_valid(row):
            excluded['invalid_source_or_identity']+=1;continue
        n=row.get('model_sample_size')
        if (type(n) is not int or n<20 or row.get('push_probability')!=0
                or not isinstance(row.get('player_id'),str)
                or float(row['line']) % 1 != .5):
            excluded['unsupported_sample_identity_or_line']+=1
            continue
        eligible.append(row)
    pairs=defaultdict(lambda:defaultdict(list))
    for row in eligible:
        pairs[(audit._quote_key(row), row['quote_source_sha256'])][row['direction']].append(row)
    result=[]
    for row in sorted(eligible,key=lambda r:(utc_timestamp(r['captured_at']),r['prediction_id'])):
        opposite_rows=pairs[(audit._quote_key(row), row['quote_source_sha256'])]['under' if row['direction']=='over' else 'over']
        opposite={other['american_odds'] for other in opposite_rows
            if utc_timestamp(other['captured_at']) <= utc_timestamp(row['captured_at'])}
        q=verified_recorded_market_baseline(row)
        paired=None
        if len(opposite)==1:
            a,b=_raw(row['american_odds']),_raw(next(iter(opposite)))
            paired=a/(a+b)
        if q is not None and paired is not None and abs(q-paired)>1e-10:
            excluded['conflicting_market_pair']+=1;continue
        if len(opposite)>1:
            excluded['conflicting_market_pair']+=1;continue
        q=q if q is not None else paired
        if q is None:
            excluded['missing_market_pair']+=1;continue
        outcome=audit._verified_outcome(row)
        observed=None
        if type(outcome) is bool:
            observed=utc_timestamp(row['outcome_observed_at'])
        over=row['direction']=='over'
        result.append(dict(row=row,unit=_unit(row),entry=utc_timestamp(row['captured_at']),
            quote=utc_timestamp(row['quote_time']),start=utc_timestamp(row['game_start_time']),
            p=row['model_probability'] if over else 1-row['model_probability'],
            q=q if over else 1-q,n=row['model_sample_size'],
            y=(int(outcome) if over else 1-int(outcome)) if type(outcome) is bool else None,
            observed=observed))
    return result,dict(excluded)


def earliest_units(observed):
    seen=set();result=[]
    for item in sorted(observed,key=lambda x:(x['entry'],x['row']['prediction_id'])):
        if item['unit'] not in seen:
            seen.add(item['unit']);result.append(item)
    return result


def fit_residual_weight(history, target):
    """Same-game labels and outcomes not yet authenticated are excluded."""
    train=[x for x in history if x['y'] is not None and x['observed'] is not None
        and x['observed']<target['entry'] and x['entry']<target['entry']
        and x['unit'][0]!=target['unit'][0]]
    games={x['unit'][0] for x in train}
    if len(games)<PROTOCOL['minimum_training_games']:
        return None,len(games)
    # Equal game, then player within game, then market/line within player.
    players=defaultdict(set);counts=Counter((x['unit'][0],x['unit'][1]) for x in train)
    for x in train:players[x['unit'][0]].add(x['unit'][1])
    numerator=denominator=0.
    for x in train:
        w=1/(len(players[x['unit'][0]])*counts[x['unit'][0],x['unit'][1]])
        delta=x['p']-x['q']
        numerator+=w*delta*(x['y']-x['q']);denominator+=w*delta*delta
    return (min(1.,max(0.,numerator/denominator)) if denominator else 0.),len(games)


def score(rows, prediction):
    pairs=[(x,prediction(x)) for x in rows if x['y'] is not None]
    pairs=[(x,p) for x,p in pairs if p is not None]
    if not pairs:return {'observations':0,'games':0}
    if any(not math.isfinite(p) or not 0<=p<=1 for _,p in pairs):
        raise ValueError('Invalid candidate probability')
    groups=defaultdict(list)
    for x,p in pairs:groups[x['unit'][0]].append((p-x['y'])**2-(x['q']-x['y'])**2)
    return {'observations':len(pairs),'games':len(groups),
        'brier':mean((p-x['y'])**2 for x,p in pairs),
        'same_rows_market_brier':mean((x['q']-x['y'])**2 for x,_ in pairs),
        'model_minus_market_brier':mean(v for group in groups.values() for v in group),
        'game_cluster_95':cluster_interval(groups)}


def cluster_interval(groups):
    """Resample whole games; one game cannot estimate between-game uncertainty."""
    if len(groups)<2:
        return None
    rng=random.Random(PROTOCOL['bootstrap_seed']);games=sorted(groups);draws=[]
    for _ in range(PROTOCOL['bootstrap_samples']):
        sample=[groups[rng.choice(games)] for _ in games]
        draws.append(sum(map(sum,sample))/sum(map(len,sample)))
    draws.sort()
    return [draws[int(len(draws)*.025)],draws[int(len(draws)*.975)]]


def cross_book_candidates(observed):
    """Reference other books from the same retained source response, never self."""
    groups=defaultdict(list)
    for x in observed:
        groups[x['unit']+(x['row']['quote_source_sha256'],)].append(x)
    proposals=[];coverage=Counter()
    for key,items in sorted(groups.items()):
        # One receipt per book/side; duplicate later scans cannot move decision time.
        unique={};prices=defaultdict(set)
        for x in sorted(items,key=lambda v:(v['entry'],v['row']['prediction_id'])):
            side=(x['row']['sportsbook'],x['row']['direction'])
            prices[side].add(x['row']['american_odds'])
            unique.setdefault(side,x)
        ambiguous={book for (book,side),odds in prices.items() if len(odds)>1}
        items=[x for (book,side),x in unique.items() if book not in ambiguous]
        coverage['ambiguous_books']+=len(ambiguous)
        if not items:continue
        decision=max(x['entry'] for x in items)
        fresh=[x for x in items if 0<=(decision-x['quote']).total_seconds()<=PROTOCOL['quote_max_age_seconds'] and decision<x['start']]
        books=defaultdict(list)
        for x in fresh:books[x['row']['sportsbook']].append(x)
        # Conflicting same-book probabilities cannot vote in the reference.
        reference={book:xs[0]['q'] for book,xs in books.items() if max(x['q'] for x in xs)-min(x['q'] for x in xs)<=1e-10}
        coverage['quote_groups']+=1
        if len(reference)<2:coverage['fewer_than_two_books']+=1;continue
        coverage['comparable_quote_groups']+=1
        for x in fresh:
            book=x['row']['sportsbook']
            if book not in reference:continue
            others=[q for b,q in reference.items() if b!=book]
            q=median(others);prob=q if x['row']['direction']=='over' else 1-q
            odds=x['row']['american_odds'];profit=odds/100 if odds>0 else 100/-odds
            ev=prob*(profit+1)-1
            if ev>=PROTOCOL['cross_book_minimum_expected_return']:
                proposals.append(dict(x=x,decision=decision,ev=ev,probability=prob,
                    reference_books=len(others),profit=profit))
    # At most one hypothetical selection per player/game, earliest qualifying batch;
    # within that instant, highest estimated EV, then stable identity. No outcomes.
    proposals.sort(key=lambda c:(c['decision'],-c['ev'],c['x']['row']['prediction_id']))
    selected=[];seen=set()
    for c in proposals:
        identity=c['x']['unit'][:2]
        if identity not in seen:seen.add(identity);selected.append(c)
    return selected,dict(coverage)


def replay(rows,sport,version):
    observed,excluded=observations(rows,sport,version);units=earliest_units(observed)
    fitted={};training=Counter()
    for x in units:
        weight,games=fit_residual_weight(units,x);training['eligible' if weight is not None else 'insufficient_prior_settled_games']+=1
        if weight is not None:fitted[x['unit']]=(weight,x['q']+weight*(x['p']-x['q']))
    scores={
        'recorded_model':score(units,lambda x:x['p']),
        'market':score(units,lambda x:x['q']),
        'market_prior80':score(units,lambda x:(x['n']*x['p']+PROTOCOL['market_prior_strength']*x['q'])/(x['n']+PROTOCOL['market_prior_strength'])),
        'past_only_fitted_residual':score(units,lambda x:fitted.get(x['unit'],(None,None))[1]),
    }
    selected,coverage=cross_book_candidates(observed);decided=[c for c in selected if c['x']['y'] is not None]
    returns=[];return_groups=defaultdict(list)
    for c in decided:
        won=bool(c['x']['y'])==(c['x']['row']['direction']=='over')
        value=c['profit'] if won else -1.
        returns.append(value);return_groups[c['x']['unit'][0]].append(value)
    weights=[v[0] for v in fitted.values()]
    return {'sport':sport,'model_version':version,'promote':False,'protocol':PROTOCOL,
        'recorded_quote_rows':len(observed),'unique_units':len(units),'excluded':excluded,
        'scores':scores,'by_market':{prop:score([x for x in units if x['unit'][2]==prop],lambda x:x['p']) for prop in sorted({x['unit'][2] for x in units})},
        'training':dict(training),'fitted_weight_range':[min(weights),max(weights)] if weights else None,
        'cross_book':{'coverage':coverage,'selected':len(selected),'decided':len(decided),
            'games':len({c['x']['unit'][0] for c in decided}),'wins':sum(v>0 for v in returns),
            'flat_stake_roi':mean(returns) if returns else None,
            'roi_game_cluster_95':cluster_interval(return_groups),
            'pending':len(selected)-len(decided),
            'selection_ids':[c['x']['row']['prediction_id'] for c in selected],
            'scope':'exploratory counterfactual prices; no new accepted picks or executed bets'},
        'limitations':['Historical outcomes were already inspected; this is not an untouched confirmatory holdout.',
            'Past-only fitting requires authenticated outcomes observed before entry, and excludes same-game labels.',
            'Market anchoring can reduce model error without producing an edge against the market.',
            'Other books are not guaranteed independent or sharper; two-book references may be weak.',
            'Game bootstrap does not account for repeated players across games; few games yield unstable intervals.',
            'Candidate recipes are research only; production qualification and frozen evaluators are unchanged.']}


class OfflineLedger(Ledger):
    def __init__(self,path):
        self.path=Path(path).resolve()
        if not self.path.is_file():raise ValueError('Existing ledger required')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)
        try:
            db.execute('PRAGMA query_only=ON');yield db
        finally:
            db.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ledger-path',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--sport',choices=['nfl','nba','cfb','all'],default='all')
    p.add_argument('--model-version',default='empirical-jeffreys-v4');args=p.parse_args()
    rows=OfflineLedger(args.ledger_path).predictions();report={'observed_at':datetime.now(timezone.utc).isoformat(),
        'source_sha256':hashlib.sha256(args.ledger_path.read_bytes()).hexdigest(),
        'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'reports':{}}
    for sport in ['nfl','nba','cfb'] if args.sport=='all' else [args.sport]:
        report['reports'][sport]=replay(rows,sport,args.model_version)
        print(json.dumps({'sport':sport,'status':'completed','promote':False}),flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')

if __name__=='__main__':main()
