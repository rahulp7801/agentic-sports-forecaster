import assert from 'node:assert/strict';
import test from 'node:test';
import {NO_STORE_HEADERS,PUBLIC_CACHE_HEADERS,liveCacheHeadersUntil,slateCacheHeadersUntil,gameLogCacheHeaders,signalCacheHeaders} from '../lib/publicCache.ts';
test('owner data never enters browser or shared CDN caches, including historical research',()=>{
  const now=Date.parse('2026-10-04T17:00:00Z');
  const headers=[...Object.values(PUBLIC_CACHE_HEADERS),liveCacheHeadersUntil([now+120000],now),
    slateCacheHeadersUntil([{game_time:new Date(now+3600000).toISOString()}],now),
    gameLogCacheHeaders(null,now),gameLogCacheHeaders('2026-10-03T00:00:00Z',now),
    ...['qualified','library','candidates'].map(signalCacheHeaders)];
  for(const h of headers) for(const key of Object.keys(NO_STORE_HEADERS)) assert.equal(h[key],'no-store');
});
