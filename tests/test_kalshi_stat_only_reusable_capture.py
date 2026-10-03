"""The reusable paper quote path cannot widen its fixed scope or sign reads."""
import asyncio
from datetime import datetime, timezone

import pytest

from sportsbet.quant.kalshi_market_cohort import digest
from sportsbet.quant.kalshi_stat_only_exact_quote import UnsignedReader, capture


def frozen():
    rows=[{'ticker':ticker,'scheduled_game_start_time':'2026-10-11T16:00:00+00:00'}
          for ticker in ('B','A')]
    return {'protocol':'kalshi-nfl-stat-only-forward-transfer-v1',
            'generated_at':'2026-10-11T12:00:00+00:00',
            'forecast_sha256':digest(rows),'forecasts':rows}


class Reader:
    def __init__(self):
        self.calls=[]

    async def quoted_markets(self,tickers):
        self.calls.append(tickers)
        return {'markets':[],'cursor':''}


def test_exact_capture_uses_only_fixed_sorted_tickers_and_stays_unsigned():
    source=frozen()
    times=iter(datetime.fromisoformat(value) for value in (
        '2026-10-11T12:00:01+00:00','2026-10-11T12:00:02+00:00',
        '2026-10-11T12:00:03+00:00','2026-10-11T12:00:04+00:00'))
    reader=Reader()
    result=asyncio.run(capture(source,reader,now=lambda:next(times)))
    assert reader.calls==[['A','B']]
    assert result['evidence']['requested_tickers']==['A','B']
    assert result['evidence_sha256']==digest(result['evidence'])
    with pytest.raises(RuntimeError,match='Authenticated request forbidden'):
        UnsignedReader._headers(None,'/trade-api/v2/markets')


@pytest.mark.parametrize('moment',[
    '2026-10-11T12:05:01+00:00',
    '2026-10-11T15:00:00+00:00',
])
def test_stale_or_locked_forecast_makes_zero_public_requests(moment):
    reader=Reader()
    with pytest.raises(ValueError,match='aged out|board lock'):
        asyncio.run(capture(frozen(),reader,now=lambda:datetime.fromisoformat(moment)))
    assert reader.calls==[]


def test_changed_forecast_commitment_makes_zero_public_requests():
    source=frozen()
    source['forecasts'][0]['ticker']='NEW'
    reader=Reader()
    with pytest.raises(ValueError,match='forecast receipt changed'):
        asyncio.run(capture(source,reader,now=lambda:datetime.now(timezone.utc)))
    assert reader.calls==[]
