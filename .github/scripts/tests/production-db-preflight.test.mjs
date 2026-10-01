import test from 'node:test';
import assert from 'node:assert/strict';
import {preflight,PATHS} from '../production-db-preflight.mjs';

test('preflight requires two rounds and fresh supported database reads',async()=>{
  const calls=[];const waits=[];
  const result=await preflight({fetcher:async (url,options)=>{
    calls.push({url,options});return {status:200};
  },sleep:async ms=>waits.push(ms)});
  assert.deepEqual(result,{rounds:2,reads:6});
  assert.equal(calls.length,6);assert.deepEqual(waits,[5000]);
  for(const round of [0,1]) {
    const current=calls.slice(round*3,round*3+3);
    assert.deepEqual(current.slice(0,2).map(call=>call.url.pathname),PATHS.map(p=>new URL(p,'https://example.test').pathname));
    assert.equal(current[0].url.search,'');
    assert.equal(current[1].url.searchParams.get('sport'),'nfl');
    assert.equal(current[1].url.searchParams.size,1);
    assert.equal(current[2].url.pathname,'/api/gamelogs');
    assert.equal(current[2].url.searchParams.get('sport'),'nfl');
    assert.equal(current[2].url.searchParams.get('limit'),'1');
    assert.match(current[2].url.searchParams.get('player'),/^HealthProbe[A-Z]{16}$/);
    assert.equal(current[2].url.searchParams.size,3);
  }
  assert.notEqual(calls[2].url.href,calls[5].url.href);
  for(const call of calls){
    assert.equal(call.options.cache,'no-store');assert.equal(call.options.redirect,'error');
    assert.equal(call.options.headers['Cache-Control'],'no-cache');
  }
});

test('old iad1 database outage can pass only for pending pdx1 recovery',async()=>{
  const calls=[];
  const fetcher=async url=>{
    calls.push(url.pathname);
    if(url.pathname==='/') return {status:200};
    return {status:503,headers:new Headers({'x-vercel-id':'sfo1::iad1::synthetic'})};
  };
  assert.deepEqual(await preflight({fetcher,sleep:async()=>{},rounds:2,delayMs:0,recoveryRegion:'pdx1'}),
    {rounds:2,reads:6,recoveringReads:6});
  assert.equal(calls.filter(path=>path==='/').length,1);
});

test('recovery blocks other regions, failures, or unavailable homepage',async()=>{
  const failed=async (status,region,home=200)=>{
    const fetcher=async url=>url.pathname==='/' ? {status:home} :
      {status,headers:new Headers({'x-vercel-id':'sfo1::'+region+'::synthetic'})};
    await assert.rejects(preflight({fetcher,sleep:async()=>{},rounds:1,recoveryRegion:'pdx1'}));
  };
  await failed(503,'pdx1');
  await failed(503,'sfo1');
  await failed(502,'iad1');
  await failed(503,'iad1',503);
  await assert.rejects(preflight({fetcher:async()=>({
    status:503,headers:new Headers({'x-vercel-id':'sfo1::iad1::synthetic'})}),
    sleep:async()=>{},rounds:1,recoveryRegion:null}));
});

test('database failure or timeout blocks deployment without exposing response bodies',async()=>{
  for(const fetcher of [async()=>({status:503}),async()=>{throw new Error('private host and credential');}]) {
    await assert.rejects(preflight({fetcher,sleep:async()=>{},rounds:1}),error=>
      error.message.startsWith('Production database preflight failed: /api/scans')
      && !error.message.includes('private host'));
  }
});