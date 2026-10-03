import test from 'node:test';
import assert from 'node:assert/strict';
import {listKalshiResearch} from '../lib/kalshiResearch.ts';
import {publicRequest} from '../lib/publicRequest.ts';

const NOW=Date.parse('2026-10-01T18:00:00Z');
const EVENT='KXNBAGAME-26OCT03MIATOR';
const row={
  ticker:EVENT+'-MIA',event_ticker:EVENT,title:'Miami wins',
  status:'active',occurrence_datetime:'2026-10-04T02:00:00Z',
  yes_bid_dollars:'0.4700',yes_bid_size_fp:'1.00',
  yes_ask_dollars:'0.5000',yes_ask_size_fp:'977.17',
  no_bid_dollars:'0.5000',no_ask_dollars:'0.5300',
};
function fixture(data,calls) {
  return async url=>{calls.push(url.href);return Response.json(data);};
}
test('open Kalshi games retain exact source quotes and ask size',async()=>{
  const calls=[];
  const data={cursor:'',events:[{event_ticker:EVENT,series_ticker:'KXNBAGAME',
    title:'Miami vs Toronto',markets:[row]}]};
  const result=await listKalshiResearch('nba',fixture(data,calls),NOW);
  assert.equal(result.source,'Kalshi');
  assert.equal(result.events.length,1);
  assert.equal(result.events[0].markets[0].yes_bid,0.47);
  assert.equal(result.events[0].markets[0].yes_ask,0.5);
  assert.equal(result.events[0].markets[0].yes_ask_size,977.17);
  assert.equal(result.events[0].markets[0].url,
    'https://kalshi.com/markets_by_ticker/'+EVENT+'-MIA');
  assert.deepEqual(calls,['https://external-api.kalshi.com/trade-api/v2/events?series_ticker=KXNBAGAME&status=open&with_nested_markets=true&limit=100']);
});
test('missing size removes ask and crossed books are excluded',async()=>{
  const calls=[];
  const noSize={...row,yes_ask_size_fp:'0.00'};
  const crossed={...row,ticker:EVENT+'-TOR',yes_bid_dollars:'0.90',yes_ask_dollars:'0.10'};
  const data={cursor:'next',events:[{event_ticker:EVENT,series_ticker:'KXNBAGAME',
    title:'Miami vs Toronto',markets:[noSize,crossed]}]};
  const result=await listKalshiResearch('nba',fixture(data,calls),NOW);
  assert.equal(result.events[0].markets.length,1);
  assert.equal(result.events[0].markets[0].yes_ask,null);
  assert.equal(result.events[0].markets[0].yes_ask_size,null);
  assert.match(result.scope,/additional events may be omitted/);
});
test('wrong series and past events cannot appear in another league',async()=>{
  const calls=[];
  const data={cursor:'',events:[
    {event_ticker:EVENT,series_ticker:'KXNBAGAME',title:'Wrong series',markets:[row]},
    {event_ticker:'KXNFLGAME-26SEP01OLD',series_ticker:'KXNFLGAME',
      title:'Old game',markets:[{...row,ticker:'KXNFLGAME-26SEP01OLD-A',
        event_ticker:'KXNFLGAME-26SEP01OLD',occurrence_datetime:'2026-09-01T02:00:00Z'}]},
  ]};
  const result=await listKalshiResearch('nfl',fixture(data,calls),NOW);
  assert.equal(result.events.length,0);
  await assert.rejects(listKalshiResearch('other',fixture(data,calls),NOW),/Invalid league/);
});
test('public request boundary only accepts one sport parameter',()=>{
  const check=url=>publicRequest({url,method:'GET',headers:new Headers()});
  assert.equal(check('https://example.test/api/kalshi-research?sport=cfb'),null);
  assert.equal(check('https://example.test/api/kalshi-research?sport=nfl&target=https://evil.test'),400);
  assert.equal(check('https://example.test/api/kalshi-research?sport=nfl&sport=nba'),400);
});
test('inconsistent complementary quotes cannot be displayed',async()=>{
  const calls=[];
  const badAsk={...row,no_bid_dollars:'0.4000'};
  const badBid={...row,ticker:EVENT+'-TOR',no_ask_dollars:'0.6200'};
  const noComplement={...row,ticker:EVENT+'-OTHER',no_bid_dollars:undefined,
    no_ask_dollars:undefined};
  const data={cursor:'',events:[{event_ticker:EVENT,series_ticker:'KXNBAGAME',
    title:'Miami vs Toronto',markets:[badAsk,badBid,noComplement]}]};
  const result=await listKalshiResearch('nba',fixture(data,calls),NOW);
  assert.deepEqual(result.events[0].markets.map(market=>market.ticker),
    [EVENT+'-MIA',EVENT+'-TOR']);
  assert.equal(result.events[0].markets[0].yes_bid,0.47);
  assert.equal(result.events[0].markets[0].yes_ask,null);
  assert.equal(result.events[0].markets[1].yes_bid,null);
  assert.equal(result.events[0].markets[1].yes_ask,0.5);
});
test('a contract with a different occurrence time is not grouped under the game',async()=>{
  const calls=[];
  const later={...row,ticker:EVENT+'-TOR',occurrence_datetime:'2026-10-05T02:00:00Z'};
  const data={cursor:'',events:[{event_ticker:EVENT,series_ticker:'KXNBAGAME',
    title:'Miami vs Toronto',markets:[row,later]}]};
  const result=await listKalshiResearch('nba',fixture(data,calls),NOW);
  assert.equal(result.events[0].starts_at,'2026-10-04T02:00:00.000Z');
  assert.deepEqual(result.events[0].markets.map(market=>market.ticker),[EVENT+'-MIA']);
});
test('CFB accepts a zero-priced opposite bid while hiding a zero-size YES ask',async()=>{
  const calls=[];
  const event='KXNCAAFGAME-26OCT03AKRCMU';
  const market={...row,ticker:event+'-AKR',event_ticker:event,
    occurrence_datetime:'2026-10-03T20:00:00Z',
    yes_bid_dollars:'0.9900',yes_bid_size_fp:'46057.27',
    yes_ask_dollars:'1.0000',yes_ask_size_fp:'0.00',
    no_bid_dollars:'0.0000',no_ask_dollars:'0.0100'};
  const data={cursor:'',events:[{event_ticker:event,series_ticker:'KXNCAAFGAME',
    title:'Akron vs Central Michigan',markets:[market]}]};
  const result=await listKalshiResearch('cfb',fixture(data,calls),NOW);
  assert.equal(result.events.length,1);
  assert.equal(result.events[0].markets[0].yes_bid,0.99);
  assert.equal(result.events[0].markets[0].yes_ask,null);
  assert.equal(result.events[0].markets[0].yes_ask_size,null);
});
