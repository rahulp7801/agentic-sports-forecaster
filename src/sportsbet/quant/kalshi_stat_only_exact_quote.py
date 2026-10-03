"""One unsigned public exact-ticker quote read for a fresh fixed NFL forecast.

No order, credential or paid sportsbook request is available from this module.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Callable

from sportsbet.ingestion.kalshi import KalshiReader
from sportsbet.quant.kalshi_market_cohort import clock, digest

VERSION='kalshi-nfl-stat-only-exact-quote-v1'
FORECAST_VERSION='kalshi-nfl-stat-only-forward-transfer-v1'


class UnsignedReader(KalshiReader):
    def _headers(self, path: str) -> dict[str,str]:
        raise RuntimeError('Authenticated request forbidden in public quote capture')


async def capture(frozen: dict, reader: KalshiReader,
                  *, now: Callable[[],datetime]) -> dict:
    if (frozen.get('protocol')!=FORECAST_VERSION
            or frozen.get('forecast_sha256')!=digest(frozen['forecasts'])):
        raise ValueError('Frozen forecast receipt changed')
    tickers=sorted(row['ticker'] for row in frozen['forecasts'])
    if not 0<len(tickers)<=200 or len(set(tickers))!=len(tickers):
        raise ValueError('Invalid bounded exact-ticker set')
    generated=clock(frozen['generated_at'])
    first_lock=min(clock(row['scheduled_game_start_time'])-timedelta(hours=1)
                   for row in frozen['forecasts'])
    started=now()
    if (started.utcoffset() is None or not 0<(started-generated).total_seconds()<=300
            or started>=first_lock):
        raise ValueError('Model forecast aged out or board lock passed')
    pages=[]
    for offset in range(0,len(tickers),20):
        batch=tickers[offset:offset+20]
        request_time=now()
        if (request_time.utcoffset() is None
                or not generated<request_time<first_lock
                or (request_time-generated).total_seconds()>300):
            raise ValueError('Price request aged out or passed board lock')
        try:
            body=await reader.quoted_markets(batch)
            page={'tickers':batch,'request_started_at':request_time.isoformat(),
                  'received_at':now().isoformat(),'body':body}
        except Exception as exc:
            page={'tickers':batch,'request_started_at':request_time.isoformat(),
                  'received_at':now().isoformat(),
                  'error_type':type(exc).__name__}
        pages.append(page)
    end=now()
    if (end.utcoffset() is None or end>=first_lock or end<clock(pages[-1]['received_at'])
            or (end-generated).total_seconds()>300):
        raise ValueError('Exact quote capture aged out before save')
    evidence={'protocol':VERSION,'forecast_sha256':frozen['forecast_sha256'],
              'forecast_receipt_sha256':digest(frozen),
              'requested_tickers':tickers,'captured_at':end.isoformat(),'pages':pages}
    return {'evidence':evidence,'evidence_sha256':digest(evidence)}


async def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecast',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Exact quote receipt already exists')
    if (args.forecast.is_symlink() or not args.forecast.is_file()
            or not 0<args.forecast.stat().st_size<=500_000):
        parser.error('Frozen forecast missing or unbounded')
    frozen=json.loads(args.forecast.read_text(encoding='utf-8'))
    async with UnsignedReader() as reader:
        receipt=await capture(frozen,reader,now=lambda:datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(receipt,stream,sort_keys=True,indent=2,allow_nan=False)
    print(json.dumps({'requested':len(receipt['evidence']['requested_tickers']),
        'pages':len(receipt['evidence']['pages']),
        'unavailable_pages':sum('error_type' in p for p in receipt['evidence']['pages']),
        'captured_at':receipt['evidence']['captured_at'],
        'evidence_sha256':receipt['evidence_sha256']},sort_keys=True))


if __name__=='__main__':
    asyncio.run(main())
