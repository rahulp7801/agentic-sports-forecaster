import assert from 'node:assert/strict';
import test from 'node:test';

import {
  paidPipelinePaths,
  publicSecurityProbes,
  publicPipelinePaths,
  requiredCssMarkers,
  requiredHtmlMarkers,
  readinessStatuses,
  verifyProduction,
  verifyProductionWithRetry,
  verifySecurityHeaders,
} from '../scripts/verify-production.mjs';

// Independent example of the current server-rendered landing contract. Do not
// synthesize this fixture from the verifier's own required marker array.
const deploymentHtml = `<html><head><link rel="stylesheet" href="/app.css"></head><body>
<section id="results"><p>Compare with constant directions</p>
<table aria-label="Same-record direction comparison"><tr><th>Model</th><td>84.5%</td></tr><tr><th>Always Under</th><td>85.0%</td></tr><tr><th>Always Over</th><td>15.0%</td></tr></table>
<table aria-label="Same-record direction comparison"><tr><th>Model</th><td>82.0%</td></tr><tr><th>Always Under</th><td>77.0%</td></tr><tr><th>Always Over</th><td>23.0%</td></tr></table>
<p>Archived sportsbook prices are unavailable; prospective profitability remains unproven.</p>
</section></body></html>`;
const deploymentCss = requiredCssMarkers.join(' ');
const securityHeaderValues = {
  'x-content-type-options': 'nosniff',
  'x-frame-options': 'DENY',
  'referrer-policy': 'strict-origin-when-cross-origin',
  'cross-origin-opener-policy': 'same-origin',
  'cross-origin-resource-policy': 'same-origin',
  'x-dns-prefetch-control': 'off',
  'origin-agent-cluster': '?1',
  'x-permitted-cross-domain-policies': 'none',
  'cache-control': 'no-store',
  'strict-transport-security': 'max-age=63072000; includeSubDomains',
  'permissions-policy': 'camera=(), microphone=()',
  'content-security-policy': "default-src 'self'; script-src 'self' 'nonce-YWJjZA==' 'strict-dynamic'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
};
const securityHeaders = { get: name => securityHeaderValues[name.toLowerCase()] ?? null };

function securityProbeStatus(path, options = {}) {
  const method = (options.method ?? 'GET').toUpperCase();
  const headers = new Headers(options.headers);
  const probe = publicSecurityProbes.find(candidate => candidate.path === path
    && (candidate.options?.method ?? 'GET') === method
    && Object.entries(candidate.options?.headers ?? {}).every(([name, value]) => headers.get(name) === value));
  return probe?.statuses[0];
}

test('production security policy requires nonce scripts and isolation headers', () => {
  assert.doesNotThrow(() => verifySecurityHeaders(securityHeaders));
  assert.throws(() => verifySecurityHeaders({ get: name => name === 'content-security-policy'
    ? "default-src 'self'; script-src 'self' 'unsafe-inline'" : securityHeaders.get(name) }), /CSP/);
});

test('readiness rejects a stale deployment missing free research routes without reading providers', async () => {
  for (const route of ['/api/kalshi-research?sport=invalid', '/api/polymarket?sport=invalid']) {
    assert.ok(publicSecurityProbes.some(probe => probe.path === route && probe.statuses.includes(400)));
    const fetchImpl = async (url, options = {}) => {
      const path = new URL(url).pathname + new URL(url).search;
      if (path === '/app.css') return {status: 200, text: async () => deploymentCss};
      return {status: path === route ? 404 : securityProbeStatus(path, options) ?? 200,
        headers: securityHeaders, text: async () => deploymentHtml};
    };
    await assert.rejects(verifyProduction({base: 'https://example.test', fetchImpl}),
      new RegExp(`${route.replace('?', '\\?')}: unexpected HTTP 404`));
  }
});

test('public pipeline makes public endpoints mandatory without requiring paid endpoints', () => {
  const flags = { paidEnabled: false, publicEnabled: true };
  for (const path of publicPipelinePaths) assert.deepEqual(readinessStatuses(path, flags), [200]);
  for (const path of paidPipelinePaths) assert.deepEqual(readinessStatuses(path, flags), [200, 503]);
});

test('paid pipeline makes all data endpoints mandatory', () => {
  const flags = { paidEnabled: true, publicEnabled: false };
  for (const path of [...paidPipelinePaths, ...publicPipelinePaths]) {
    assert.deepEqual(readinessStatuses(path, flags), [200]);
  }
});

test('production verification rejects unavailable public data when its pipeline is enabled', async () => {
  const fetchImpl = async (url, options = {}) => {
    const path = new URL(url).pathname + new URL(url).search;
    if (path === '/app.css') return { status: 200, text: async () => deploymentCss };
    const status = path === '/api/markets?sport=nfl' ? 503 : securityProbeStatus(path, options)
      ?? (path === '/.env' || path === '/signals_cache.json' ? 404 : 200);
    return {
      status,
      headers: securityHeaders,
      text: async () => deploymentHtml,
    };
  };

  await assert.rejects(
    verifyProduction({ base: 'https://example.test', fetchImpl, paidEnabled: false, publicEnabled: true }),
    /\/api\/markets\?sport=nfl: unexpected HTTP 503/,
  );
});

test('public readiness retries only a transient mandatory 503 without recollecting', async () => {
  const target='/api/gamelogs?sport=cfb&player_id=1&exact=1&limit=1';
  const counts=new Map(),waits=[];
  const fetchImpl=async(url,options={})=>{
    const parsed=new URL(url),path=parsed.pathname+parsed.search;
    counts.set(path,(counts.get(path)??0)+1);
    if(path==='/app.css')return {status:200,text:async()=>deploymentCss};
    const status=path===target && counts.get(path)<3 ? 503 : securityProbeStatus(path,options)
      ?? (['/.env','/signals_cache.json'].includes(path)?404:200);
    return {status,headers:securityHeaders,text:async()=>deploymentHtml,json:async()=>({})};
  };
  await verifyProduction({base:'https://example.test',fetchImpl,paidEnabled:false,publicEnabled:true,
    transient503Attempts:3,transient503DelayMs:5000,
    transient503Wait:async delay=>waits.push(delay)});
  assert.equal(counts.get(target),3);
  assert.equal(counts.get('/api/markets?sport=nfl'),1);
  assert.deepEqual(waits,[5000,5000]);
});

test('public readiness still fails after the bounded 503 window', async () => {
  const target='/api/gamelogs?sport=cfb&player_id=1&exact=1&limit=1';
  let reads=0;
  const fetchImpl=async(url,options={})=>{
    const parsed=new URL(url),path=parsed.pathname+parsed.search;
    if(path==='/app.css')return {status:200,text:async()=>deploymentCss};
    if(path===target)reads++;
    return {status:path===target?503:securityProbeStatus(path,options)
      ?? (['/.env','/signals_cache.json'].includes(path)?404:200),
      headers:securityHeaders,text:async()=>deploymentHtml,json:async()=>({})};
  };
  await assert.rejects(verifyProduction({base:'https://example.test',fetchImpl,
    paidEnabled:false,publicEnabled:true,transient503Attempts:3,
    transient503DelayMs:0,transient503Wait:async()=>{}}),
  /\/api\/gamelogs\?sport=cfb.*unexpected HTTP 503/);
  assert.equal(reads,3);
});

test('production verification binds public endpoints to the current collection report', async () => {
  const expectedPublicReport = {
    markets: { nfl: { captured_at: '2026-09-12T23:14:02Z' } },
    schedules: { nfl: { captured_at: '2026-09-12T23:13:52Z' } },
  };
  const fetchImpl = async (url, options = {}) => {
    const parsed = new URL(url);
    const path = parsed.pathname + parsed.search;
    if (path === '/app.css') return { status: 200, text: async () => deploymentCss };
    const captured_at = path === '/api/markets?sport=nfl'
      ? '2026-09-12T23:14:02Z'
      : path === '/api/games?sport=nfl'
        ? '2026-09-12T23:13:52Z'
        : undefined;
    return {
      status: securityProbeStatus(path, options) ?? (path === '/.env' || path === '/signals_cache.json' ? 404 : 200),
      headers: securityHeaders,
      text: async () => deploymentHtml,
      json: async () => ({ captured_at }),
    };
  };

  await verifyProduction({
    base: 'https://example.test',
    fetchImpl,
    paidEnabled: false,
    publicEnabled: true,
    expectedPublicReport,
  });

  expectedPublicReport.markets.nfl.captured_at = '2026-09-12T23:15:02Z';
  await assert.rejects(
    verifyProduction({
      base: 'https://example.test',
      fetchImpl,
      paidEnabled: false,
      publicEnabled: true,
      expectedPublicReport,
    }),
    /deployed capture does not match this collection run/,
  );
});

test('production verification rejects a stale or incomplete stylesheet bundle', async () => {
  const fetchImpl = async (url, options = {}) => {
    const path = new URL(url).pathname + new URL(url).search;
    if (path === '/app.css') return { status: 200, text: async () => ':root{--accent-mint:#00e5a0}' };
    return {
      status: securityProbeStatus(path, options) ?? (path === '/.env' || path === '/signals_cache.json' ? 404 : 200),
      headers: securityHeaders,
      text: async () => deploymentHtml,
      json: async () => ({}),
    };
  };

  await assert.rejects(
    verifyProduction({ base: 'https://example.test', fetchImpl }),
    /Production stylesheet is stale or incomplete/,
  );
});

test('production verification retries a transient deployment propagation mismatch', async () => {
  let stylesheetRequests = 0;
  const fetchImpl = async (url, options = {}) => {
    const path = new URL(url).pathname + new URL(url).search;
    if (path === '/app.css') {
      stylesheetRequests += 1;
      return { status: 200, text: async () => stylesheetRequests === 1 ? ':root{}' : deploymentCss };
    }
    return {
      status: securityProbeStatus(path, options) ?? (path === '/.env' || path === '/signals_cache.json' ? 404 : 200),
      headers: securityHeaders,
      text: async () => deploymentHtml,
      json: async () => ({}),
    };
  };

  const waits = [];
  await verifyProductionWithRetry(
    { base: 'https://example.test', fetchImpl },
    { attempts: 2, delayMs: 25, wait: async delay => waits.push(delay), log: () => {} },
  );
  assert.equal(stylesheetRequests, 2);
  assert.deepEqual(waits, [25]);
});


test('capture retries wait for exact identity without repeating security or healthy endpoints', async () => {
  const expected='2026-09-24T18:05:50.066420+00:00';
  const counts=new Map();let waited=0;
  const fetchImpl=async(url,options={})=>{
    const parsed=new URL(url),path=parsed.pathname+parsed.search;
    counts.set(path,(counts.get(path)??0)+1);
    if(path==='/app.css')return {status:200,text:async()=>deploymentCss};
    if(path==='/api/markets?sport=nfl') {
      assert.equal(options.cache,'no-store');assert.equal(options.headers['cache-control'],'no-cache');
    }
    return {status:securityProbeStatus(path,options)??(['/.env','/signals_cache.json'].includes(path)?404:200),
      headers:securityHeaders,text:async()=>deploymentHtml,
      json:async()=>({captured_at:path==='/api/markets?sport=nfl' && waited===0 ? '2026-09-24T17:52:17Z' : expected})};
  };
  await verifyProduction({base:'https://example.test',fetchImpl,paidEnabled:false,publicEnabled:true,
    expectedPublicReport:{markets:{nfl:{captured_at:expected}},schedules:{nba:{captured_at:expected}}},
    captureAttempts:3,captureDelayMs:5000,captureWait:async delay=>{assert.equal(delay,5000);waited++;}});
  assert.equal(waited,1);assert.equal(counts.get('/api/markets?sport=nfl'),2);
  assert.equal(counts.get('/api/games?sport=nba'),1);
  assert.equal(counts.get('/api/scan'),1);assert.equal(counts.get('/app.css'),1);
});

for(const observed of ['2026-09-24T17:00:00Z','2026-09-24T19:00:00Z',undefined]) {
  test(`capture retries fail closed for persistently different identity: ${observed}`,async()=>{
    let reads=0,waits=0;
    const fetchImpl=async(url,options={})=>{
      const parsed=new URL(url),path=parsed.pathname+parsed.search;
      if(path==='/app.css')return {status:200,text:async()=>deploymentCss};
      if(path==='/api/markets?sport=nfl')reads++;
      return {status:securityProbeStatus(path,options)??(['/.env','/signals_cache.json'].includes(path)?404:200),
        headers:securityHeaders,text:async()=>deploymentHtml,json:async()=>({captured_at:observed})};
    };
    await assert.rejects(verifyProduction({base:'https://example.test',fetchImpl,
      expectedPublicReport:{markets:{nfl:{captured_at:'2026-09-24T18:05:50.066420+00:00'}}},
      captureAttempts:3,captureDelayMs:0,captureWait:async()=>{waits++;}}),/deployed capture does not match/);
    assert.equal(reads,3);assert.equal(waits,2);
  });
}

test('public capture retry settings are bounded before any requests',async()=>{
  for(const patch of [{captureAttempts:0},{captureAttempts:38},{captureAttempts:1.5},
    {captureDelayMs:-1},{captureDelayMs:5001},{captureDelayMs:NaN},
    {transient503Attempts:0},{transient503Attempts:4},{transient503Attempts:1.5},
    {transient503DelayMs:-1},{transient503DelayMs:5001}]) {
    await assert.rejects(verifyProduction({...patch,fetchImpl:async()=>{assert.fail('must not request');}}),/retry bounds/);
  }
});


test('production readiness covers CFB consumer forecasts, replay, slate and history',()=>{
  for(const path of ['/api/signals?sport=cfb&limit=12','/api/signals?sport=cfb&view=qualified',
    '/api/picks?sport=cfb','/api/metrics?sport=cfb','/api/metrics?sport=cfb&cohort=recommendations']) {
    assert.ok(paidPipelinePaths.includes(path));
    assert.deepEqual(readinessStatuses(path,{paidEnabled:true,publicEnabled:true}),[200]);
  }
  for(const path of ['/api/slate?sport=cfb','/api/gamelogs?sport=cfb&player_id=1&exact=1&limit=1',
    '/api/gamelogs?sport=cfb&player_id=1&exact=1&limit=1&before=2026-10-02&observed_before=2026-10-01T23%3A00%3A00Z',
    '/api/benchmarks?sport=cfb']) {
    assert.ok(publicPipelinePaths.includes(path));
    assert.deepEqual(readinessStatuses(path,{paidEnabled:false,publicEnabled:true}),[200]);
  }
});


test('current baseline-aware landing contract passes the complete readiness check',async()=>{
  const fetchImpl=async(url,options={})=>{
    const parsed=new URL(url),path=parsed.pathname+parsed.search;
    return {status:securityProbeStatus(path,options)??(['/.env','/signals_cache.json'].includes(path)?404:200),
      headers:securityHeaders,text:async()=>path==='/app.css'?deploymentCss:deploymentHtml};
  };
  await verifyProduction({base:'https://example.test',fetchImpl,paidEnabled:true,publicEnabled:true});
});

test('readiness rejects legacy accuracy copy and each missing comparison or disclosure',async()=>{
  const legacy='<section id="results">Above 60% in both periods 84.5% 82.0% not betting profit</section>';
  for(const html of [legacy,...requiredHtmlMarkers.map(marker=>deploymentHtml.replaceAll(marker,''))]) {
    let reads=0;
    await assert.rejects(verifyProduction({base:'https://example.test',fetchImpl:async()=>{
      reads++;return {status:200,headers:securityHeaders,text:async()=>html};
    }}),/Production landing evidence is stale or incomplete/);
    assert.equal(reads,1);
  }
});

test('readiness rejects a deployment that cannot serve as-of history for any sport',async()=>{
  const targets=publicPipelinePaths.filter(path=>path.startsWith('/api/gamelogs?')
    && path.includes('observed_before='));
  assert.deepEqual(targets.map(path=>new URL(path,'https://example.test').searchParams.get('sport')),
    ['nfl','nba','cfb']);
  for(const target of targets){
    const fetchImpl=async(url,options={})=>{
      const parsed=new URL(url),path=parsed.pathname+parsed.search;
      if(path==='/app.css')return {status:200,text:async()=>deploymentCss};
      return {status:path===target?400:securityProbeStatus(path,options)
        ?? (['/.env','/signals_cache.json'].includes(path)?404:200),
        headers:securityHeaders,text:async()=>deploymentHtml,json:async()=>({})};
    };
    await assert.rejects(verifyProduction({base:'https://example.test',fetchImpl,
      paidEnabled:false,publicEnabled:true}),error=>error.message.includes(target)
      && error.message.includes('unexpected HTTP 400'));
  }
});
