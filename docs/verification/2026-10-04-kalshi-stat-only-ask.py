"""Offline fixed 5-point gross ask screen on one forward exact quote receipt."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
from sportsbet.quant.kalshi_market_cohort import clock,digest
from sportsbet.quant.kalshi_exact_markout import _market_state,_side_asks
from sportsbet.quant.kalshi_ask_policy import decision,one_per_player_game,MIN_GROSS_MARGIN

F=Path('.local/kalshi-stat-only-probabilities-20261004.json')
Q=Path('.local/kalshi-stat-only-quotes-20261004.json')
O=Path('.local/verified-timely-pair-20261003/market-archive.json')
C=Path('.local/verified-timely-pair-20261003/pair.json')
OUT=Path('.local/kalshi-stat-only-ask-decisions-20261004.json')

def main():
    if OUT.exists() or OUT.is_symlink(): raise FileExistsError('Decision receipt exists')
    f=json.loads(F.read_text(encoding='utf-8'))
    q=json.loads(Q.read_text(encoding='utf-8'))
    archive=json.loads(O.read_text(encoding='utf-8'))
    pair=json.loads(C.read_text(encoding='utf-8'))
    evidence=q['evidence']
    if (f['protocol']!='kalshi-nfl-stat-only-forward-transfer-v1'
        or f['forecast_sha256']!=digest(f['forecasts'])
        or q['evidence_sha256']!=digest(evidence)
        or evidence['forecast_receipt_sha256']!=digest(f)
        or evidence['forecast_sha256']!=f['forecast_sha256']):
        raise ValueError('Frozen model or quote receipt changed')
    forecasts={row['ticker']:row for row in f['forecasts']}
    tickers=sorted(forecasts)
    if evidence['requested_tickers']!=tickers or len(evidence['pages'])!=(len(tickers)+19)//20:
        raise ValueError('Exact ticker scope changed')
    original={row['ticker']:row for row in archive['evidence']['sources']['kalshi']['prop_inventory']['quotes']}
    offers={row['ticker']:row for row in pair['cohort']['selections']}
    now=datetime.now(timezone.utc)
    generated=clock(f['generated_at'])
    first_lock=min(clock(row['scheduled_game_start_time'])-timedelta(hours=1) for row in f['forecasts'])
    if (not generated < clock(evidence['captured_at']) <= now
            or not 0 < (now-generated).total_seconds() <= 300 or now >= first_lock):
        raise ValueError('Decision must follow quote and precede expiry and board lock')
    market_by_ticker={}
    missing=Counter()
    for index,page in enumerate(evidence['pages']):
        batch=tickers[index*20:(index+1)*20]
        started,received=clock(page['request_started_at']),clock(page['received_at'])
        if (page['tickers']!=batch or not generated<started<=received<=clock(evidence['captured_at'])
                or received>=first_lock or (received-generated).total_seconds()>300):
            raise ValueError('Exact quote chronology changed')
        if 'error_type' in page:
            missing['batch_unavailable']+=len(batch)
            continue
        body=page['body']
        rows=body.get('markets') if isinstance(body,dict) else None
        if (not isinstance(rows,list) or body.get('cursor') not in (None,'')
                or any(not isinstance(row,dict) for row in rows)):
            raise ValueError('Incomplete exact ticker page')
        returned=[row.get('ticker') for row in rows]
        if len(returned)!=len(set(returned)) or not set(returned)<=set(batch):
            raise ValueError('Extra or duplicate exact market')
        market_by_ticker.update({row['ticker']:row for row in rows})
    eligible=[]
    quote_counts=Counter()
    for ticker in tickers:
        market=market_by_ticker.get(ticker)
        if market is None:
            quote_counts['missing_or_failed']+=1
            continue
        old=original[ticker]
        yes_state,yes=_market_state(market,old,'yes')
        no_state,no=_market_state(market,old,'no')
        if yes_state!='prelock_exact_ask' or no_state!='prelock_exact_ask':
            quote_counts[f'{yes_state}|{no_state}']+=1
            continue
        sides=_side_asks(market)
        offer=dict(offers[ticker])
        offer['yes_ask']={'cost':str(yes),'displayed_size':str(sides['yes'][1])}
        offer['no_ask']={'cost':str(no),'displayed_size':str(sides['no'][1])}
        choice=decision(offer,forecasts[ticker])
        if choice is None:
            quote_counts['below_5pp']+=1
        else:
            choice['price_received_at']=next(page['received_at'] for page in evidence['pages'] if ticker in page['tickers'])
            choice['model_version']=f['frozen_model_version']
            eligible.append(choice)
            quote_counts['above_5pp']+=1
    # The fixed cap uses highest margin, then exact ticker, with no outcome information.
    candidates=one_per_player_game(eligible)
    receipt={'protocol':'kalshi-nfl-stat-only-ask-paper-v1','decided_at':now.isoformat(),
             'model_receipt_sha256':digest(f),'quote_receipt_sha256':digest(q),
             'model_forecast_sha256':f['forecast_sha256'],
             'minimum_gross_margin':str(MIN_GROSS_MARGIN),
             'eligible_model_contracts':f['eligible_contracts'],
             'model_forecasts':len(tickers),'quote_state_counts':dict(sorted(quote_counts.items())),
             'above_margin_before_cap':len(eligible),
             'one_per_player_game_excluded':len(eligible)-len(candidates),
             'candidates_count':len(candidates),
             'candidate_games':len({row['milestone_id'] for row in candidates}),
             'candidates_sha256':digest(candidates),'candidates':candidates,
             'authenticated_settlements':0,'fills_verified':False,'roi':None,'clv':None,
             'edge_established':False,'qualified_picks':0,'execution_ready':False}
    if sum(quote_counts.values())!=len(tickers): raise AssertionError('Price denominator changed')
    with OUT.open('x',encoding='utf-8') as stream:
        json.dump(receipt,stream,indent=2,sort_keys=True,allow_nan=False)
    print(json.dumps({key:receipt[key] for key in ('protocol','decided_at','eligible_model_contracts',
        'model_forecasts','quote_state_counts','above_margin_before_cap',
        'one_per_player_game_excluded','candidates_count','candidate_games',
        'candidates_sha256','edge_established')},sort_keys=True))

main()
