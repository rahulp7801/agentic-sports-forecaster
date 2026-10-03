import assert from 'node:assert/strict';
import test from 'node:test';

import {NO_STORE_HEADERS,PUBLIC_CACHE_HEADERS,liveCacheHeadersUntil,slateCacheHeadersUntil,gameLogCacheHeaders,signalCacheHeaders} from '../lib/publicCache.ts';

test('public data stays out of browser caches while Vercel absorbs repeat reads',()=>{
  for(const headers of Object.values(PUBLIC_CACHE_HEADERS)) {
    assert.equal(headers['Cache-Control'],'no-store');
    assert.match(headers['Vercel-CDN-Cache-Control'],/^public, s-maxage=\d+, stale-while-revalidate=\d+$/);
  }
  for(const key of ['Cache-Control','CDN-Cache-Control','Vercel-CDN-Cache-Control']) assert.equal(NO_STORE_HEADERS[key],'no-store');
});

test('actionable forecasts use the shortest cache lifetime',()=>{
  assert.equal(signalCacheHeaders('qualified'),PUBLIC_CACHE_HEADERS.live);
  assert.equal(signalCacheHeaders('candidates'),PUBLIC_CACHE_HEADERS.research);
  assert.equal(signalCacheHeaders('library'),PUBLIC_CACHE_HEADERS.research);
  const live=Number(PUBLIC_CACHE_HEADERS.live['Vercel-CDN-Cache-Control'].match(/s-maxage=(\d+)/)?.[1]);
  const research=Number(PUBLIC_CACHE_HEADERS.research['Vercel-CDN-Cache-Control'].match(/s-maxage=(\d+)/)?.[1]);
  assert.ok(live>0 && live<research && research<=300);
});

test('live CDN cache expires before the earliest pick or evidence deadline',()=>{
  const now=Date.parse('2026-10-04T13:00:00Z');
  assert.equal(liveCacheHeadersUntil([],now),PUBLIC_CACHE_HEADERS.live);
  const bounded=liveCacheHeadersUntil([now+50_000,now+300_000],now);
  assert.equal(bounded['Cache-Control'],'no-store');
  assert.equal(bounded['Vercel-CDN-Cache-Control'],
    'public, s-maxage=30, stale-while-revalidate=18');
  assert.equal(liveCacheHeadersUntil([now+31_000],now)['Vercel-CDN-Cache-Control'],
    'public, s-maxage=29');
  assert.equal(liveCacheHeadersUntil([now+2_000],now),NO_STORE_HEADERS);
  assert.equal(liveCacheHeadersUntil([Number.NaN],now),NO_STORE_HEADERS);
  assert.equal(liveCacheHeadersUntil([now+60_000],Number.NaN),NO_STORE_HEADERS);
});

test('slate cache expires before both the one-hour lock and kickoff',()=>{
  const start=Date.parse('2026-10-04T17:00:00Z');
  const games=[{game_time:new Date(start).toISOString()}];
  assert.equal(slateCacheHeadersUntil(games,start-60*60000-1000),NO_STORE_HEADERS);
  assert.deepEqual(slateCacheHeadersUntil(games,start-60*60000),PUBLIC_CACHE_HEADERS.live);
  assert.equal(slateCacheHeadersUntil(games,start-1000),NO_STORE_HEADERS);
  assert.equal(slateCacheHeadersUntil(games,start),PUBLIC_CACHE_HEADERS.status);
  assert.equal(slateCacheHeadersUntil([{game_time:'invalid'}],start),NO_STORE_HEADERS);
});

test('live player history refreshes sooner than a fixed past forecast cutoff',()=>{
  const now=Date.parse('2026-10-04T17:00:00Z');
  assert.equal(gameLogCacheHeaders(null,now),PUBLIC_CACHE_HEADERS.research);
  assert.equal(gameLogCacheHeaders('2026-10-04T16:00:00Z',now),PUBLIC_CACHE_HEADERS.archive);
  assert.equal(gameLogCacheHeaders('2026-10-04T18:00:00Z',now),PUBLIC_CACHE_HEADERS.research);
});
