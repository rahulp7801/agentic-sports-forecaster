import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

export const paidPipelinePaths = [
  '/api/signals',
  '/api/signals?sport=nfl&limit=12',
  '/api/signals?sport=nba&limit=12',
  '/api/signals?sport=cfb&limit=12',
  '/api/signals?sport=cfb&view=qualified',
  '/api/picks?sport=cfb',
  '/api/metrics?sport=cfb',
  '/api/metrics?sport=cfb&cohort=recommendations',
  '/api/signals?sport=nfl&view=qualified',
  '/api/signals?sport=nba&view=qualified',
  '/api/picks?sport=nfl',
  '/api/picks?sport=nba',
  '/api/metrics',
  '/api/metrics?cohort=recommendations',
  '/api/scans',
  '/api/prop-screens?sport=nfl',
  '/api/prop-screens?sport=nba',
];

export const publicPipelinePaths = [
  '/api/slate?sport=nfl',
  '/api/slate?sport=nba',
  '/api/slate?sport=cfb',
  '/api/gamelogs?sport=cfb&player_id=1&exact=1&limit=1',
  '/api/gamelogs?sport=cfb&player_id=1&exact=1&limit=1&before=2026-10-02&observed_before=2026-10-01T23%3A00%3A00Z',
  '/api/benchmarks?sport=cfb',
  '/api/markets?sport=nfl',
  '/api/markets?sport=nba',
  '/api/games?sport=nfl',
  '/api/games?sport=nba',
  '/api/gamelogs?sport=nfl',
  '/api/gamelogs?sport=nba',
  '/api/gamelogs?sport=nfl&player_id=00-0000001&exact=1&limit=1',
  '/api/benchmarks?sport=nfl',
  '/api/benchmarks?sport=nba',
];

export const requiredCssMarkers = [
  '--accent:#5e5ce6',
  '.terminal-layout{',
  '__hero h1{',
  '__demo{',
];

export const requiredHtmlMarkers = [
  'id="results"',
  'Compare with constant directions',
  'Same-record direction comparison',
  'Always Under',
  'Always Over',
  '85.0%',
  '77.0%',
  '84.5%',
  '82.0%',
  'prospective profitability remains unproven',
];

export const publicSecurityProbes = [
  { path: '/api/scan', statuses: [403], options: { method: 'POST' } },
  { path: '/api/scans', statuses: [403], options: { headers: { 'sec-fetch-site': 'same-site' } } },
  { path: '/api/scans', statuses: [403], options: { headers: { origin: 'https://attacker.invalid' } } },
  { path: '/api/signals?sport=nfl&offset=1000', statuses: [400] },
  { path: '/api/gamelogs?sport=nfl&player=%25', statuses: [400] },
  { path: '/api/picks?sport=mlb', statuses: [400] },
  // Invalid leagues are rejected by these route handlers before any free-provider read.
  // A stale deployment with no route or proxy allowlist returns 404 instead.
  { path: '/api/kalshi-research?sport=invalid', statuses: [400] },
  { path: '/api/polymarket?sport=invalid', statuses: [400] },
];

export function readinessStatuses(path, { paidEnabled, publicEnabled }) {
  if (paidPipelinePaths.includes(path)) return paidEnabled ? [200] : [200, 503];
  if (publicPipelinePaths.includes(path)) return paidEnabled || publicEnabled ? [200] : [200, 503];
  throw new Error(`Unclassified readiness endpoint: ${path}`);
}

export function verifySecurityHeaders(headers) {
  const expected = {
    'x-content-type-options': 'nosniff',
    'x-frame-options': 'DENY',
    'referrer-policy': 'strict-origin-when-cross-origin',
    'cross-origin-opener-policy': 'same-origin',
    'cross-origin-resource-policy': 'same-origin',
    'x-dns-prefetch-control': 'off',
    'origin-agent-cluster': '?1',
    'x-permitted-cross-domain-policies': 'none',
  };
  for (const [name, value] of Object.entries(expected)) {
    if (headers.get(name) !== value) throw new Error(`Production security header is missing or invalid: ${name}`);
  }
  if (!headers.get('strict-transport-security')?.includes('max-age=63072000')) {
    throw new Error('Production HSTS policy is missing or invalid');
  }
  if (!headers.get('permissions-policy')?.includes('camera=()')) {
    throw new Error('Production permissions policy is missing or invalid');
  }
  const policy = headers.get('content-security-policy') || '';
  for (const directive of ["default-src 'self'", "script-src 'self'", "'strict-dynamic'", "object-src 'none'",
    "base-uri 'self'", "form-action 'self'", "frame-ancestors 'none'", "connect-src 'self'"]) {
    if (!policy.includes(directive)) throw new Error(`Production CSP is missing: ${directive}`);
  }
  if (!/'nonce-[A-Za-z0-9+/=]+'/.test(policy) || /script-src[^;]*'unsafe-inline'/.test(policy)
      || /script-src[^;]*'unsafe-eval'/.test(policy)) {
    throw new Error('Production script CSP does not enforce a nonce');
  }
}

function expectedPublicCapture(path, report) {
  if (!report) return undefined;
  const url = new URL(path, 'https://readiness.invalid');
  const sport = url.searchParams.get('sport');
  if (url.pathname === '/api/markets') return report.markets?.[sport]?.captured_at;
  if (url.pathname === '/api/games') return report.schedules?.[sport]?.captured_at;
  return undefined;
}

export async function verifyProduction({
  base = process.env.PRODUCTION_BASE_URL || 'https://agentic-ev-analytics-platform.vercel.app',
  fetchImpl = fetch,
  paidEnabled = process.env.DATA_PIPELINE_ENABLED === 'true',
  publicEnabled = process.env.PUBLIC_DATA_PIPELINE_ENABLED === 'true',
  expectedPublicReport,
  captureAttempts = 1,
  captureDelayMs = 5000,
  captureWait = delay => new Promise(resolve => setTimeout(resolve, delay)),
  transient503Attempts = 1,
  transient503DelayMs = 5000,
  transient503Wait = delay => new Promise(resolve => setTimeout(resolve, delay)),
} = {}) {
  if (!Number.isInteger(captureAttempts) || captureAttempts < 1 || captureAttempts > 37
      || !Number.isInteger(captureDelayMs) || captureDelayMs < 0 || captureDelayMs > 5000
      || !Number.isInteger(transient503Attempts) || transient503Attempts < 1 || transient503Attempts > 3
      || !Number.isInteger(transient503DelayMs) || transient503DelayMs < 0 || transient503DelayMs > 5000) {
    throw new Error('Invalid production retry bounds');
  }
  base = base.replace(/\/$/, '');
  async function check(path, expected, options = {}) {
    for (let attempt = 1; attempt <= transient503Attempts; attempt++) {
      const response = await fetchImpl(base + path, {
        ...options,
        signal: AbortSignal.timeout(20000),
        redirect: 'manual',
      });
      if (expected.includes(response.status)) return response;
      if (response.status !== 503 || attempt === transient503Attempts) {
        throw new Error(`${path}: unexpected HTTP ${response.status}`);
      }
      console.log(`::warning::${path} returned transient HTTP 503 (${attempt}/${transient503Attempts})`);
      await transient503Wait(transient503DelayMs);
    }
  }

  const cacheKey = encodeURIComponent(process.env.GITHUB_SHA || Date.now().toString());
  const home = await check(`/?readiness=${cacheKey}`, [200], {
    cache: 'no-store',
    headers: { 'cache-control': 'no-cache' },
  });
  verifySecurityHeaders(home.headers);
  const html = await home.text();
  for (const marker of requiredHtmlMarkers) {
    if (!html.includes(marker)) throw new Error(`Production landing evidence is stale or incomplete: ${marker}`);
  }
  const stylesheetUrls = [...html.matchAll(/href=["']([^"']+\.css(?:\?[^"']*)?)["']/gi)]
    .map(match => new URL(match[1], base).toString());
  if (!stylesheetUrls.length) throw new Error('Production stylesheets are missing');
  const css = (await Promise.all(stylesheetUrls.map(async url => {
    const response = await fetchImpl(url, { signal: AbortSignal.timeout(20000), redirect: 'manual' });
    if (response.status !== 200) throw new Error(`Production stylesheet returned HTTP ${response.status}`);
    return response.text();
  }))).join('\n');
  for (const marker of requiredCssMarkers) {
    if (!css.includes(marker)) throw new Error(`Production stylesheet is stale or incomplete: ${marker}`);
  }
  for (const probe of publicSecurityProbes) {
    const response = await check(probe.path, probe.statuses, probe.options);
    if (!response.headers.get('cache-control')?.includes('no-store')) {
      throw new Error(`${probe.path}: rejected request may be cached`);
    }
  }
  await check('/.env', [404]);
  await check('/signals_cache.json', [404]);

  let pendingCaptures = [];
  const captureOptions = {cache: 'no-store', headers: {'cache-control': 'no-cache'}};
  for (const path of [...paidPipelinePaths, ...publicPipelinePaths]) {
    const response = await check(path, readinessStatuses(path, { paidEnabled, publicEnabled }), captureOptions);
    if (response.status === 503) {
      console.log(`::warning::${path} unavailable; its data pipeline is disabled`);
    }
    const capturedAt = expectedPublicCapture(path, expectedPublicReport);
    if (capturedAt !== undefined) {
      const body = await response.json();
      if (body?.captured_at !== capturedAt) {
        pendingCaptures.push({path, capturedAt});
      }
    }
  }
  // CDN and server data caches can each serve one stale response while refreshing.
  // Retry only unmatched public captures; retain the exact run identity requirement.
  for (let attempt = 1; pendingCaptures.length && attempt < captureAttempts; attempt++) {
    console.log(`::warning::${pendingCaptures.length} public capture(s) awaiting cache refresh (${attempt}/${captureAttempts})`);
    await captureWait(captureDelayMs);
    const results = await Promise.all(pendingCaptures.map(async capture => {
      const response = await check(capture.path, [200], captureOptions);
      const body = await response.json();
      return body?.captured_at === capture.capturedAt ? null : capture;
    }));
    pendingCaptures = results.filter(Boolean);
  }
  if (pendingCaptures.length) {
    throw new Error(`${pendingCaptures[0].path}: deployed capture does not match this collection run`);
  }
}

export async function verifyProductionWithRetry(
  options = {},
  {
    attempts = 1,
    delayMs = 0,
    wait = delay => new Promise(resolve => setTimeout(resolve, delay)),
    log = message => console.log(message),
  } = {},
) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      await verifyProduction(options);
      return;
    } catch (error) {
      lastError = error;
      if (attempt === attempts) break;
      log(`::warning::Production verification attempt ${attempt}/${attempts} failed: ${error.message}`);
      await wait(delayMs);
    }
  }
  throw lastError;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const expectedPublicReport = process.env.PUBLIC_DATA_REPORT_PATH
    ? JSON.parse(await readFile(process.env.PUBLIC_DATA_REPORT_PATH, 'utf8'))
    : undefined;
  const attempts = Number.parseInt(process.env.PRODUCTION_VERIFY_ATTEMPTS || '1', 10);
  const delayMs = Number.parseInt(process.env.PRODUCTION_VERIFY_DELAY_MS || '0', 10);
  await verifyProductionWithRetry(
    { expectedPublicReport,
      captureAttempts: Number(process.env.PUBLIC_CAPTURE_VERIFY_ATTEMPTS || '1'),
      captureDelayMs: Number(process.env.PUBLIC_CAPTURE_VERIFY_DELAY_MS || '5000'),
      transient503Attempts: Number(process.env.PUBLIC_READINESS_503_ATTEMPTS || '1'),
      transient503DelayMs: Number(process.env.PUBLIC_READINESS_503_DELAY_MS || '5000') },
    { attempts: Number.isInteger(attempts) && attempts > 0 ? attempts : 1,
      delayMs: Number.isInteger(delayMs) && delayMs >= 0 ? delayMs : 0 },
  );
}
