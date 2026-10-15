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
  '/api/gamelogs?sport=nfl&player_id=00-0000001&exact=1&limit=1&before=2026-10-02&observed_before=2026-10-01T23%3A00%3A00Z',
  '/api/gamelogs?sport=nba&player_id=1&exact=1&limit=1&before=2026-10-02&observed_before=2026-10-01T23%3A00%3A00Z',
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

export const requiredHtmlMarkers=['id="waitlist"','id="backtest-demo"','Illustrative preview','Sample layout','Private preview','Join the waitlist','Owner sign-in'];
export const livePaths=[...new Set([...paidPipelinePaths,...publicPipelinePaths,
  '/api/kalshi-research?sport=nfl','/api/polymarket?sport=nfl','/api/scan'])];
export const publicSecurityProbes=[
  {path:'/api/scan',statuses:[403],options:{method:'POST'}},
  {path:'/api/scans',statuses:[403],options:{headers:{origin:'https://attacker.invalid'}}},
  {path:'/api/signals?sport=nfl&sport=nba',statuses:[400]},
  {path:'/api/waitlist',statuses:[405]},
  {path:'/api/waitlist',statuses:[403],options:{method:'POST',headers:{origin:'https://attacker.invalid'}}},
];
export function readinessStatuses() {return [401];}

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

/** Assert source publication through restricted DB reads; never export an owner cookie to CI. */
export async function verifyPublishedCaptures(report,read) {
  const entries=[];
  for(const sport of ['nfl','nba','cfb']) for(const [category,prefix] of [['markets','markets'],['schedules','schedule'],['slates','slate']]) {
    const captured=report?.[category]?.[sport]?.captured_at;
    if(captured!==undefined) {
      if(typeof captured!=='string' || !Number.isFinite(Date.parse(captured))) throw Error('Invalid capture receipt');
      entries.push([prefix+':'+sport,captured]);
    }
  }
  if(!entries.length) throw Error('No capture receipts to verify');
  for(const [key,captured] of entries) {
    if((await read(key))?.captured_at!==captured) throw Error(key+': published capture does not match this run');
  }
}
async function readPublishedSnapshot(key) {
  const {Client}=await import('pg');
  const {hosted_read_dsn}=await import('./verify-published-config.mjs');
  const config=hosted_read_dsn(process.env.DATABASE_URL,process.env.DATABASE_SSL_CA);
  const client=new Client({...config,connectionTimeoutMillis:5000,statement_timeout:5000,query_timeout:6000});
  try {await client.connect();const result=await client.query('SELECT payload FROM public.dashboard_snapshots WHERE snapshot_key=$1',[key]);return result.rows[0]?.payload;}
  catch {throw Error('Published snapshot read unavailable');}
  finally {await client.end().catch(()=>{});}
}
export async function verifyProduction({base=process.env.PRODUCTION_BASE_URL || 'https://agentic-ev-analytics-platform.vercel.app',
  fetchImpl=fetch,expectedPublicReport,readSnapshot=readPublishedSnapshot}={}) {
  base=base.replace(/\/$/,'');
  async function check(path,statuses,options={}) {
    const response=await fetchImpl(base+path,{...options,redirect:'manual',cache:'no-store',signal:AbortSignal.timeout(20000)});
    if(!statuses.includes(response.status)) throw Error(path+': unexpected HTTP '+response.status);
    return response;
  }
  function noStore(response,path) {
    if(!response.headers.get('cache-control')?.includes('no-store'))throw Error(path+': response may be cached');
    for(const header of ['cdn-cache-control','vercel-cdn-cache-control']) {
      // Vercel consumes its internal CDN header; when present it must remain private.
      const value=response.headers.get(header);if(value && value!=='no-store')throw Error(path+': shared cache header');
    }
  }
  const home=await check('/?readiness='+encodeURIComponent(process.env.GITHUB_SHA || Date.now()),[200]);
  verifySecurityHeaders(home.headers);const html=await home.text();
  for(const marker of requiredHtmlMarkers)if(!html.includes(marker))throw Error('Production landing is stale or incomplete: '+marker);
  const styles=[...html.matchAll(/href=["']([^"']+\.css(?:\?[^"']*)?)["']/gi)].map(match=>new URL(match[1],base));
  if(!styles.length)throw Error('Production stylesheets are missing');
  const css=(await Promise.all(styles.map(async url=>{const response=await fetchImpl(url,{redirect:'manual',signal:AbortSignal.timeout(20000)});if(response.status!==200)throw Error('Production stylesheet unavailable');return response.text();}))).join('\n');
  for(const marker of requiredCssMarkers)if(!css.includes(marker))throw Error('Production stylesheet is stale or incomplete: '+marker);
  for(const path of livePaths) {
    const response=await check(path,[401]);noStore(response,path);
    const body=await response.json();if(body?.error!=='Owner authentication required.')throw Error(path+': unexpected authentication response');
  }
  for(const path of ['/terminal','/terminal?readiness=1','/terminal/nfl']) {
    const response=await check(path,[307]);noStore(response,path);
    if(new URL(response.headers.get('location') || '',base).pathname!=='/login')throw Error(path+': owner login redirect missing');
  }
  const login=await check('/login',[200]);noStore(login,'/login');
  if(!(await login.text()).includes('Owner access'))throw Error('Owner login page missing');
  for(const probe of publicSecurityProbes)noStore(await check(probe.path,probe.statuses,probe.options),probe.path);
  await check('/.env',[404]);noStore(await check('/signals_cache.json',[401]),'/signals_cache.json');
  // This read-only probe never submits a real email or triggers outbound mail.
  const csrf=await check('/api/auth/csrf',[200]);noStore(csrf,'/api/auth/csrf');
  if(typeof (await csrf.json()).csrfToken!=='string')throw Error('Owner authentication configuration is not ready');
  if(expectedPublicReport)await verifyPublishedCaptures(expectedPublicReport,readSnapshot);
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
