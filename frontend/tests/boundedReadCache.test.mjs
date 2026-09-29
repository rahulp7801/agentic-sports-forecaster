import test from 'node:test';
import assert from 'node:assert/strict';
import {BoundedReadCache} from '../lib/boundedReadCache.ts';
const options={maxEntries:2,maxBytes:100,maxEntryBytes:50,maxPending:2};
test('coalesces misses, clones results and expires without stale fallback',async()=>{
 let now=0,calls=0;const c=new BoundedReadCache(options,()=>now);
 const load=async()=>{calls++;return {value:1};};
 const [a,b]=await Promise.all([c.read('a',10,load),c.read('a',10,load)]);
 assert.equal(calls,1);a.value=9;assert.equal(b.value,1);assert.equal((await c.read('a',10,load)).value,1);
 now=10;await assert.rejects(c.read('a',10,async()=>{throw new Error('offline');}));
 assert.equal(c.size,0);assert.equal(c.pendingCount,0);
 await c.read('a',10,load);assert.equal(calls,2);
});
test('bounds LRU cardinality, byte usage and oversized values',async()=>{
 const c=new BoundedReadCache(options);await c.read('a',1000,async()=>({x:1}));await c.read('b',1000,async()=>({x:2}));
 await c.read('a',1000,async()=>{throw new Error('hit expected');});await c.read('c',1000,async()=>({x:3}));
 let missed=false;await c.read('b',1000,async()=>{missed=true;return {x:2};});assert.ok(missed);assert.equal(c.size,2);
 await c.read('huge',1000,async()=>('x'.repeat(100)));assert.equal(c.size,2);assert.ok(c.byteSize<=100);
});
test('caps distinct pending loads while permitting shared waiters',async()=>{
 const c=new BoundedReadCache({...options,maxPending:1});let resolve;
 const pending=c.read('a',1000,()=>new Promise(r=>resolve=r));await Promise.resolve();
 const shared=c.read('a',1000,async()=>{throw new Error('must not load');});
 await assert.rejects(c.read('b',1000,async()=>1),/Service busy/);resolve({x:1});await Promise.all([pending,shared]);assert.equal(c.pendingCount,0);
});
