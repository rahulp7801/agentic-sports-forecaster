"""Offline exploratory edge search and robustness checks; no strategy promotion."""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from statistics import mean,median

from sportsbet.quant import market_challengers as frozen

PROTOCOL={
    'version':'edge-search-stress-v1','minimum_expected_return':.02,
    'maximum_quote_age_seconds':300,'market_prior_strength':80,
    'policies':['raw_model','market_prior80','cross_book','cross_book_model_agrees','cross_book_prior80_positive'],
    'winning_payout_reduction':.05,'retrospective_split':'2026-09-25T00:00:00+00:00',
    'scope':'Exploratory previously inspected archive; no confirmation or promotion',
}


def probability(x,prior=False):
    p=(x['n']*x['p']+PROTOCOL['market_prior_strength']*x['q'])/(x['n']+PROTOCOL['market_prior_strength']) if prior else x['p']
    return p if x['row']['direction']=='over' else 1-p


def profit(odds):
    return odds/100 if odds>0 else 100/-odds


def fresh(x,decision):
    return decision<x['start'] and 0<=(decision-x['quote']).total_seconds()<=PROTOCOL['maximum_quote_age_seconds']


def select_model(observed,prior=False):
    groups=defaultdict(list)
    for x in observed:
        groups[x['unit'][:2]+(x['row']['quote_source_sha256'],)].append(x)
    proposals=[]
    for xs in groups.values():
        # Fix each quote's first receipt so repeated scans cannot refresh its age.
        first={};prices=defaultdict(set)
        for x in sorted(xs,key=lambda x:(x['entry'],x['row']['prediction_id'])):
            key=x['unit']+(x['row']['sportsbook'],x['row']['direction'])
            prices[key].add(x['row']['american_odds']);first.setdefault(key,x)
        xs=[x for key,x in first.items() if len(prices[key])==1]
        if not xs:continue
        decision=max(x['entry'] for x in xs)
        for x in xs:
            p=probability(x,prior);net=profit(x['row']['american_odds']);ev=p*(net+1)-1
            if fresh(x,decision) and ev>=PROTOCOL['minimum_expected_return']:
                proposals.append(dict(x=x,decision=decision,ev=ev,probability=p,profit=net))
    selected=[];seen=set()
    for c in sorted(proposals,key=lambda c:(c['decision'],-c['ev'],c['x']['row']['prediction_id'])):
        key=c['x']['unit'][:2]
        if key not in seen:seen.add(key);selected.append(c)
    return selected


def policies(observed):
    cross,_=frozen.cross_book_candidates(observed)
    return dict(raw_model=select_model(observed),market_prior80=select_model(observed,True),
        cross_book=cross,
        cross_book_model_agrees=[c for c in cross if probability(c['x'])>(c['x']['q'] if c['x']['row']['direction']=='over' else 1-c['x']['q'])],
        cross_book_prior80_positive=[c for c in cross if probability(c['x'],True)*(c['profit']+1)-1>=PROTOCOL['minimum_expected_return']])


def result(c):
    if c['x']['y'] is None:return None
    return c['profit'] if bool(c['x']['y'])==(c['x']['row']['direction']=='over') else -1.


def metrics(selected):
    settled=[(c,result(c)) for c in selected if result(c) is not None]
    groups=defaultdict(list)
    for c,value in settled:groups[c['x']['unit'][0]].append(value)
    returns=[value for _,value in settled];total=sum(returns)
    without={game:(total-sum(values))/(len(returns)-len(values))
        for game,values in groups.items() if len(values)<len(returns)}
    best=max(groups,key=lambda game:sum(groups[game])) if groups else None
    scored=[dict(c['x'],p=c['probability'] if c['x']['row']['direction']=='over' else 1-c['probability']) for c,_ in settled]
    split=datetime.fromisoformat(PROTOCOL['retrospective_split'])
    early=[v for c,v in settled if c['x']['start']<split];late=[v for c,v in settled if c['x']['start']>=split]
    return dict(selected=len(selected),decided=len(returns),pending=len(selected)-len(returns),games=len(groups),
        wins=sum(v>0 for v in returns),flat_stake_roi=mean(returns) if returns else None,
        roi_game_cluster_95=frozen.cluster_interval(groups),probability_scores=frozen.score(scored,lambda x:x['p']),
        roi_without_best_profit_game=without.get(best),leave_one_game_out_roi_range=[min(without.values()),max(without.values())] if without else None,
        roi_with_lower_winning_payouts=mean(v*(1-PROTOCOL['winning_payout_reduction']) if v>0 else v for v in returns) if returns else None,
        pending_all_losses_roi=(total-(len(selected)-len(returns)))/len(selected) if selected else None,
        median_estimated_return=median(c['ev'] for c in selected) if selected else None,
        median_probability_cushion=median(c['probability']-1/(c['profit']+1) for c in selected) if selected else None,
        retrospective_date_split=dict(earlier_decisions=len(early),earlier_roi=mean(early) if early else None,
            later_decisions=len(late),later_roi=mean(late) if late else None),
        selections=[c['x']['row']['prediction_id'] for c in selected])


def exact_two_sided_prices(observed):
    """Conditional price arithmetic only: two verified opposite legs, no bets."""
    groups=defaultdict(list)
    for x in observed:groups[x['unit']+(x['row']['quote_source_sha256'],)].append(x)
    proposals=[]
    for xs in groups.values():
        first={};prices=defaultdict(set)
        for x in sorted(xs,key=lambda x:(x['entry'],x['row']['prediction_id'])):
            key=(x['row']['sportsbook'],x['row']['direction'])
            prices[key].add(x['row']['american_odds']);first.setdefault(key,x)
        xs=[x for key,x in first.items() if len(prices[key])==1]
        if not xs:continue
        decision=max(x['entry'] for x in xs);xs=[x for x in xs if fresh(x,decision)]
        for over in (x for x in xs if x['row']['direction']=='over'):
            for under in (x for x in xs if x['row']['direction']=='under'):
                if over['row']['sportsbook']==under['row']['sportsbook']:continue
                def decimal_price(x):
                    odds=Decimal(x['row']['american_odds'])
                    return 1+(odds/100 if odds>0 else 100/-odds)
                a,b=decimal_price(over),decimal_price(under);implied=1/a+1/b
                if implied>=1-Decimal('1e-12'):continue
                reduced=Decimal('0.95')
                adverse=1/(1+(a-1)*reduced)+1/(1+(b-1)*reduced)
                proposals.append(dict(game_id=over['unit'][0],player_id=over['unit'][1],
                    prop_type=over['unit'][2],line=over['unit'][3],decision_at=decision.isoformat(),
                    quote_ids=[over['row']['prediction_id'],under['row']['prediction_id']],
                    books=[over['row']['sportsbook'],under['row']['sportsbook']],
                    odds=[over['row']['american_odds'],under['row']['american_odds']],
                    conditional_margin=float(1/implied-1),margin_with_lower_payouts=float(1/adverse-1)))
    selected=[];seen=set()
    for p in sorted(proposals,key=lambda p:(p['decision_at'],-p['conditional_margin'],p['quote_ids'])):
        key=(p['game_id'],p['player_id'])
        if key not in seen:seen.add(key);selected.append(p)
    return dict(count=len(selected),games=len({p['game_id'] for p in selected}),
        median_conditional_margin=median(p['conditional_margin'] for p in selected) if selected else None,
        survives_lower_payouts=sum(p['margin_with_lower_payouts']>0 for p in selected),examples=selected,
        scope='Historical price discrepancies, conditional on both legs being available and identically settled. No executed or guaranteed profit.')


def run(rows,sport,version):
    observed,excluded=frozen.observations(rows,sport,version)
    results={name:metrics(selected) for name,selected in policies(observed).items()}
    return dict(sport=sport,model_version=version,observed_quotes=len(observed),excluded=excluded,
        policies=results,two_sided_prices=exact_two_sided_prices(observed),promote=False,
        limitations=['The archive was previously inspected; all policies and slices remain exploratory.',
            'Related policies and many correlated selections are not independent experiments.',
            'Removing a game is a sensitivity check, not a new holdout or training scheme.',
            'Game intervals do not adjust for strategy search or repeated players across games.',
            'Price-only margins require execution and matching settlement rules that this archive cannot establish.',
            'No production thresholds, model versions, forward tests or picks are changed.'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ledger-path',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--model-version',default='empirical-jeffreys-v4')
    args=p.parse_args();rows=frozen.OfflineLedger(args.ledger_path).predictions()
    report=dict(protocol=PROTOCOL,observed_at=datetime.now(timezone.utc).isoformat(),
        source_sha256=hashlib.sha256(args.ledger_path.read_bytes()).hexdigest(),
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        frozen_selector_sha256=hashlib.sha256(Path(frozen.__file__).read_bytes()).hexdigest(),reports={})
    for sport in ('nfl','cfb','nba'):
        report['reports'][sport]=run(rows,sport,args.model_version)
        print(sport+' exploratory checks completed',flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')


if __name__=='__main__':main()
