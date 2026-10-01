import test from 'node:test';
import assert from 'node:assert/strict';
import {listPredictionMarkets,predictionMarketDetail} from '../lib/polymarketResearch.ts';
import {publicRequest} from '../lib/publicRequest.ts';

const NOW=Date.parse('2026-10-01T18:00:00Z');
const SLUG='nfl-ari-nyg-2026-10-04-first-td-scorer';
const sports=[{sport:'nfl',series:'12185'},{sport:'nba',series:'10345'},{sport:'cfb',series:'12756'}];
const series={events:[
  {slug:SLUG,title:'Cardinals vs. Giants - First Touchdown Scorer',
    startTime:'2026-10-04T17:00:00Z',active:true,closed:false},
  {slug:'nfl-old-2026-09-01',title:'Old game',startTime:'2026-09-01T17:00:00Z',active:true,closed:false},
  {slug:'celebrity-market',title:'Unrelated',startTime:'2026-10-04T17:00:00Z',active:true,closed:false},
]};
const event={slug:SLUG,active:true,closed:false,markets:[
  {question:'Will a player score first?',outcomes:'["Yes","No"]',active:true,closed:false,acceptingOrders:true,
    bestBid:0.01,bestAsk:0.97,liquidityNum:5.82,outcomePrices:'["0.49","0.51"]'},
  {question:'Paused market',outcomes:'["Yes","No"]',active:true,closed:false,acceptingOrders:false,
    bestBid:0.4,bestAsk:0.5,liquidityNum:20},
  {question:'Crossed book',outcomes:'["Yes","No"]',active:true,closed:false,acceptingOrders:true,
    bestBid:0.99,bestAsk:0.01,liquidityNum:100},
  {question:'Closed market',outcomes:'["Yes","No"]',active:false,closed:true,acceptingOrders:false,
    bestBid:0.4,bestAsk:0.5,liquidityNum:20},
]};
function fixtureFetcher(calls) {
  return async url=>{
    calls.push(url.href);
    const body=url.pathname==='/sports' ? sports
      : url.pathname==='/series/12185' ? series
      : url.pathname==='/events/slug/'+SLUG ? event : null;
    return body===null ? new Response('',{status:404}) : Response.json(body);
  };
}
test('research listing is bounded to the matching current league series',async()=>{
  const calls=[];
  const result=await listPredictionMarkets('nfl',fixtureFetcher(calls),NOW);
  assert.deepEqual(result.events.map(item=>item.slug),[SLUG]);
  assert.equal(result.source,'Polymarket');
  assert.equal(result.observed_at,'2026-10-01T18:00:00.000Z');
  assert.deepEqual(calls,[
    'https://gamma-api.polymarket.com/sports',
    'https://gamma-api.polymarket.com/series/12185',
  ]);
});
test('event research uses the YES ask, excludes midpoint and crossed quotes',async()=>{
  const calls=[];
  const result=await predictionMarketDetail('nfl',SLUG,fixtureFetcher(calls),NOW);
  assert.equal(result.markets.length,2);
  assert.equal(result.markets[1].accepting_orders,false);
  assert.equal(result.markets[1].best_bid,null);
  assert.equal(result.markets[1].best_ask,null);
  assert.equal(result.markets[0].outcome,'Yes');
  assert.equal(result.markets[0].best_bid,0.01);
  assert.equal(result.markets[0].best_ask,0.97);
  assert.equal(result.markets[0].liquidity_usd,5.82);
  assert.equal(result.event.url,'https://polymarket.com/event/'+SLUG);
  assert.equal(calls.length,3);
  assert.ok(!JSON.stringify(result).includes('0.49'));
});
test('team-named outcomes retain their first outcome label',async()=>{
  const named=structuredClone(event);
  named.markets[0].outcomes='["Warriors","Clippers"]';
  const ordinary=fixtureFetcher([]);
  const fetcher=url=>url.pathname==='/events/slug/'+SLUG ? Response.json(named) : ordinary(url);
  const result=await predictionMarketDetail('nfl',SLUG,fetcher,NOW);
  assert.equal(result.markets[0].outcome,'Warriors');
});
test('arbitrary event paths and non-series events cannot trigger provider detail reads',async()=>{
  const calls=[];
  await assert.rejects(predictionMarketDetail('nfl','https://attacker.test/',fixtureFetcher(calls),NOW));
  assert.equal(calls.length,0);
  await assert.rejects(predictionMarketDetail('nfl','nfl-unknown-event',fixtureFetcher(calls),NOW));
  assert.equal(calls.length,2);
});
test('oversized provider response fails closed',async()=>{
  const huge=async()=>new Response('x'.repeat(512*1024+1),{headers:{'content-type':'application/json'}});
  await assert.rejects(listPredictionMarkets('nfl',huge,NOW),/too large/);
});
test('public API rejects unexpected and duplicate research parameters',()=>{
  const check=url=>publicRequest({url,method:'GET',headers:new Headers()});
  assert.equal(check('https://example.test/api/polymarket?sport=nfl'),null);
  assert.equal(check('https://example.test/api/polymarket?sport=nfl&event='+SLUG),null);
  assert.equal(check('https://example.test/api/polymarket?sport=nfl&target=https://evil.test'),400);
  assert.equal(check('https://example.test/api/polymarket?sport=nfl&sport=nba'),400);
});