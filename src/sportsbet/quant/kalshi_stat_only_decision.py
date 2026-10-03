"""Freeze the existing five-point stat-only paper policy on one exact quote receipt.

Read-only and outcome-blind: this creates no consumer pick or order.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from sportsbet.quant.kalshi_ask_policy import decision, one_per_player_game, MIN_GROSS_MARGIN
from sportsbet.quant.kalshi_market_cohort import clock, digest
from sportsbet.quant.kalshi_market_settlement import verify_cohort
from sportsbet.quant.kalshi_pair_capture import unpack
from sportsbet.quant.kalshi_stat_only_forward_eval import _price_states

VERSION='kalshi-nfl-stat-only-ask-paper-v1'
FORECAST_VERSION='kalshi-nfl-stat-only-forward-transfer-v1'


def freeze(pair: dict, original: dict, forecast: dict, quotes: dict,
           *, now: datetime) -> dict:
    cohort, shadow=unpack(pair)
    verify_cohort(original,cohort)
    if (forecast.get('protocol')!=FORECAST_VERSION
            or forecast.get('market_selection_sha256')!=cohort['selection_sha256']
            or forecast.get('source_forecasts_sha256')!=shadow['forecasts_sha256']
            or forecast.get('forecast_sha256')!=digest(forecast['forecasts'])
            or quotes.get('evidence_sha256')!=digest(quotes['evidence'])
            or quotes['evidence'].get('forecast_sha256')!=forecast['forecast_sha256']
            or quotes['evidence'].get('forecast_receipt_sha256')!=digest(forecast)):
        raise ValueError('Frozen source, forecast, or exact quote receipt changed')
    rows=forecast['forecasts']
    if not rows or len(rows)!=forecast['predicted_contracts'] or now.utcoffset() is None:
        raise ValueError('Invalid fixed forecast denominator or clock')
    generated=clock(forecast['generated_at'])
    first_lock=min(clock(row['scheduled_game_start_time'])-timedelta(hours=1) for row in rows)
    if not 0<(now-generated).total_seconds()<=300 or now>=first_lock:
        raise ValueError('Decision aged out or passed board lock')
    prices=_price_states(original,forecast,quotes,now)
    offers={row['ticker']:row for row in cohort['selections']}
    eligible=[]
    counts=Counter()
    for row in rows:
        ticker=row['ticker']
        state,_,asks,received=prices[ticker]
        if asks is None:
            counts[state]+=1
            continue
        chosen=decision(dict(offers[ticker],**asks),row)
        if chosen is None:
            counts['below_5pp']+=1
        else:
            chosen['price_received_at']=received
            chosen['model_version']=forecast['frozen_model_version']
            eligible.append(chosen)
            counts['above_5pp']+=1
    candidates=one_per_player_game(eligible)
    if sum(counts.values())!=len(rows):
        raise AssertionError('Fixed exact quote denominator changed')
    return {'protocol':VERSION,'decided_at':now.isoformat(),
            'model_receipt_sha256':digest(forecast),
            'quote_receipt_sha256':digest(quotes),
            'model_forecast_sha256':forecast['forecast_sha256'],
            'minimum_gross_margin':str(MIN_GROSS_MARGIN),
            'eligible_model_contracts':forecast['eligible_contracts'],
            'model_forecasts':len(rows),
            'quote_state_counts':dict(sorted(counts.items())),
            'above_margin_before_cap':len(eligible),
            'one_per_player_game_excluded':len(eligible)-len(candidates),
            'candidates_count':len(candidates),
            'candidate_games':len({row['milestone_id'] for row in candidates}),
            'candidates_sha256':digest(candidates),'candidates':candidates,
            'authenticated_settlements':0,'fills_verified':False,'roi':None,'clv':None,
            'edge_established':False,'qualified_picks':0,'execution_ready':False}


def _input(path: Path, maximum: int) -> dict:
    if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=maximum:
        raise ValueError('Input missing or unbounded')
    value=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value,dict):
        raise ValueError('Input is not an object')
    return value


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('pair','market','forecast','quotes'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Paper decision receipt already exists')
    pair=_input(args.pair,5_000_000)
    market=_input(args.market,25_000_000)
    forecast=_input(args.forecast,500_000)
    quotes=_input(args.quotes,2_000_000)
    receipt=freeze(pair,market,forecast,quotes,now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(receipt,stream,sort_keys=True,indent=2,allow_nan=False)
    print(json.dumps({key:receipt[key] for key in (
        'protocol','decided_at','eligible_model_contracts','model_forecasts',
        'quote_state_counts','above_margin_before_cap','one_per_player_game_excluded',
        'candidates_count','candidate_games','candidates_sha256','edge_established')},
        sort_keys=True))


if __name__=='__main__':
    main()
