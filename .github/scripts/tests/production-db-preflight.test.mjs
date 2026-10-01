import test from 'node:test';
import assert from 'node:assert/strict';
import {preflight,PATHS} from '../production-db-preflight.mjs';

test('preflight requires repeated uncached successful reads before deployment',async()=>{
  const calls=[];const waits=[];
  const result=await preflight({fetcher:async (url,options)=>{
    calls.push({url,options});return {status:200};
  },sleep:async ms=>waits.push(ms)});
  assert.deepEqual(result,{rounds:2,reads:4});
  assert.equal(calls.length,4);assert.deepEqual(waits,[5000]);
  assert.deepEqual(calls.map(call=>call.url.pathname),[...PATHS.map(p=>new URL(p,'https://example.test').pathname),...PATHS.map(p=>new URL(p,'https://example.test').pathname)]);
  for(const call of calls){
    assert.equal(call.options.cache,'no-store');assert.equal(call.options.redirect,'error');
    assert.ok(call.url.searchParams.has('health_probe'));
  }
});

test('database failure or timeout blocks deployment without exposing response bodies',async()=>{
  for(const fetcher of [async()=>({status:503}),async()=>{throw new Error('private host and credential');}]) {
    await assert.rejects(preflight({fetcher,sleep:async()=>{},rounds:1}),error=>
      error.message.startsWith('Production database preflight failed: /api/scans')
      && !error.message.includes('private host'));
  }
});