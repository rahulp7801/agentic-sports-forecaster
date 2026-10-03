import test from 'node:test';
import assert from 'node:assert/strict';
import {upcomingMarketEvents,marketResearchCacheHeaders} from '../lib/marketResearchWindow.ts';
import {NO_STORE_HEADERS,PUBLIC_CACHE_HEADERS} from '../lib/publicCache.ts';

test('retained market quotes disappear at exact event start without another provider call',()=>{
  const start=Date.parse('2026-10-04T17:00:00Z');
  const event={starts_at:new Date(start).toISOString(),ticker:'exact'};
  assert.deepEqual(upcomingMarketEvents([event],start-1),[event]);
  assert.deepEqual(upcomingMarketEvents([event],start),[]);
  assert.deepEqual(upcomingMarketEvents([event],start+1),[]);
  assert.deepEqual(upcomingMarketEvents([{starts_at:'invalid'}],start),[]);
});

test('research CDN freshness and stale lifetime both end before event start',()=>{
  const start=Date.parse('2026-10-04T17:00:00Z');
  const events=[{starts_at:new Date(start).toISOString()}];
  assert.equal(marketResearchCacheHeaders(events,start-1000),NO_STORE_HEADERS);
  assert.deepEqual(marketResearchCacheHeaders(events,start-120000),PUBLIC_CACHE_HEADERS.live);
  assert.equal(marketResearchCacheHeaders([],start),PUBLIC_CACHE_HEADERS.status);
  assert.equal(marketResearchCacheHeaders([{starts_at:'invalid'}],start),NO_STORE_HEADERS);
});
