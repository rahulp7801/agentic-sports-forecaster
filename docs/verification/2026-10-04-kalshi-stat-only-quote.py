"""One unsigned exact-ticker Kalshi quote read for pre-frozen stat-only forecasts."""
import asyncio
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from sportsbet.ingestion.kalshi import KalshiReader
from sportsbet.quant.clock_attestation import attest
from sportsbet.quant.kalshi_market_cohort import clock, digest

INPUT=Path('.local/kalshi-stat-only-probabilities-20261004.json')
OUTPUT=Path('.local/kalshi-stat-only-quotes-20261004.json')

async def main():
    frozen=json.loads(INPUT.read_text(encoding='utf-8'))
    if frozen['protocol']!='kalshi-nfl-stat-only-forward-transfer-v1' or frozen['forecast_sha256']!=digest(frozen['forecasts']):
        raise ValueError('Frozen forecast receipt changed')
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise FileExistsError('Exact quote receipt already exists')
    tickers=sorted(f['ticker'] for f in frozen['forecasts'])
    if not 0<len(tickers)<=200 or len(set(tickers))!=len(tickers):
        raise ValueError('Invalid bounded exact-ticker set')
    clock_proof=await attest()
    now=datetime.now(timezone.utc)
    if not 0<(now-clock(frozen['generated_at'])).total_seconds()<=300:
        raise ValueError('Model forecast aged out before price request')
    first_lock=min(clock(f['scheduled_game_start_time'])-timedelta(hours=1) for f in frozen['forecasts'])
    if now>=first_lock:
        raise ValueError('Pregame board lock passed')
    pages=[]
    def no_signing(*args,**kwargs): raise RuntimeError('Authenticated request forbidden')
    KalshiReader._headers=no_signing
    async with KalshiReader() as reader:
        for offset in range(0,len(tickers),20):
            batch=tickers[offset:offset+20]
            started=datetime.now(timezone.utc)
            if (started-clock(frozen['generated_at'])).total_seconds()>300 or started>=first_lock:
                raise ValueError('Price request aged out or passed board lock')
            try:
                body=await reader.quoted_markets(batch)
                page={'tickers':batch,'request_started_at':started.isoformat(),
                      'received_at':datetime.now(timezone.utc).isoformat(),'body':body}
            except Exception as exc:
                page={'tickers':batch,'request_started_at':started.isoformat(),
                      'received_at':datetime.now(timezone.utc).isoformat(),
                      'error_type':type(exc).__name__}
            pages.append(page)
    end=datetime.now(timezone.utc)
    evidence={'protocol':'kalshi-nfl-stat-only-exact-quote-v1',
              'forecast_sha256':frozen['forecast_sha256'],
              'forecast_receipt_sha256':digest(frozen),
              'requested_tickers':tickers,'captured_at':end.isoformat(),
              'clock_attestation':clock_proof,'pages':pages}
    receipt={'evidence':evidence,'evidence_sha256':digest(evidence)}
    with OUTPUT.open('x',encoding='utf-8') as stream:
        json.dump(receipt,stream,sort_keys=True,indent=2,allow_nan=False)
    print(json.dumps({'requested':len(tickers),'pages':len(pages),
                      'unavailable_pages':sum('error_type' in p for p in pages),
                      'captured_at':end.isoformat(),'evidence_sha256':receipt['evidence_sha256']},sort_keys=True))

asyncio.run(main())
