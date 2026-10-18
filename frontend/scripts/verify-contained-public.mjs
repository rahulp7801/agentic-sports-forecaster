import {pathToFileURL} from 'node:url';
import {PRODUCTION_HOST} from '../../.github/scripts/deployment-plan.mjs';
import {livePaths, requiredCssMarkers, requiredHtmlMarkers, verifySecurityHeaders} from './verify-production.mjs';

export const CONTAINED_ORIGIN = `https://${PRODUCTION_HOST}`;
export const containedPaths = [...new Set([...livePaths, '/api/signals?sport=nfl&sport=nba',
  '/terminal', '/terminal?readiness=1', '/terminal/nfl', '/signals_cache.json'])];
const LIMIT = 1024 * 1024;
const unavailable = () => Error('Contained public verification failed');

function noStore(response) {
  const cache = response.headers.get('cache-control') || '';
  if (!/(?:^|,)\s*no-store\s*(?:,|$)/i.test(cache)) throw unavailable();
  for (const directive of cache.toLowerCase().split(',').map(value => value.trim())) {
    if (directive === 'public' || (/^(?:s-maxage|max-age)\b/.test(directive)
        && !/^(?:s-maxage|max-age)\s*=\s*(?:0|"0")$/.test(directive))) throw unavailable();
  }
  for (const name of ['cdn-cache-control', 'vercel-cdn-cache-control']) {
    const value = response.headers.get(name);
    if (value !== null && value !== 'no-store') throw unavailable();
  }
}

function client(base, fetchImpl) {
  // This verifier never sends credentials or follows a landing-provided host.
  if (base !== CONTAINED_ORIGIN || typeof fetchImpl !== 'function') throw unavailable();
  const deadline = AbortSignal.timeout(60000);
  return async (path, status, options = {}) => {
    const url = new URL(path, base);
    if (url.origin !== base || url.username || url.password || url.hash) throw unavailable();
    const response = await fetchImpl(url.href, {...options, redirect: 'manual', cache: 'no-store',
      credentials: 'omit', signal: AbortSignal.any([deadline, AbortSignal.timeout(10000)])});
    if (response.status !== status) {
      await response.body?.cancel();
      throw unavailable();
    }
    return response;
  };
}

async function boundedText(response, media) {
  if (response.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase() !== media) throw unavailable();
  const size = response.headers.get('content-length');
  if (size !== null && (!/^\d+$/.test(size) || Number(size) > LIMIT)) throw unavailable();
  const reader = response.body?.getReader();
  if (!reader) throw unavailable();
  let bytes = 0;
  const chunks = [];
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > LIMIT) {await reader.cancel(); throw unavailable();}
      chunks.push(value);
    }
  } finally {reader.releaseLock();}
  const body = new Uint8Array(bytes);
  let offset = 0;
  for (const chunk of chunks) {body.set(chunk, offset); offset += chunk.byteLength;}
  return new TextDecoder('utf-8', {fatal: true}).decode(body);
}

function pendingOwnerButton(html) {
  const buttons = [...html.matchAll(/<button\b([^<>]*)>\s*Continue with GitHub\s*<\/button>/g)];
  if (buttons.length !== 1) return false;
  // Consume quoted values with their attribute so aria/data/title text cannot
  // masquerade as the HTML boolean attribute on the actual owner button.
  const attributes = [...buttons[0][1].matchAll(/\s+([^\s=/"'<>]+)(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+))?/g)];
  return attributes.some(attribute => attribute[1].toLowerCase() === 'disabled');
}

async function access(check) {
  for (const path of containedPaths) {
    const response = await check(path, 403);
    noStore(response);
    await response.body?.cancel();
  }
  const post = await check('/api/scan', 403, {method: 'POST'});
  noStore(post);
  await post.body?.cancel();
}

/** Public read-only probes of the existing hard-deny perimeter. No owner session. */
export async function verifyContainedAccess({base = CONTAINED_ORIGIN, fetchImpl = fetch} = {}) {
  try {
    await access(client(base, fetchImpl));
    return {live_routes_contained: true, owner_authentication_verified: false};
  } catch {throw unavailable();}
}

/** Verify the public preview while the exact external containment remains active. */
export async function verifyContainedPublic({base = CONTAINED_ORIGIN, fetchImpl = fetch} = {}) {
  try {
    const check = client(base, fetchImpl);
    const home = await check('/', 200);
    verifySecurityHeaders(home.headers);
    const html = await boundedText(home, 'text/html');
    if (requiredHtmlMarkers.some(marker => !html.includes(marker))) throw unavailable();
    const styles = [...new Set([...html.matchAll(/href=["']([^"']+\.css(?:\?[^"']*)?)["']/gi)]
      .map(match => match[1]))];
    if (!styles.length || styles.length > 12) throw unavailable();
    const urls = styles.map(value => {
      if (value.length > 512 || /[\x00-\x20\\]/.test(value)) throw unavailable();
      const url = new URL(value, base);
      if (url.origin !== base || url.username || url.password || url.hash || url.search.length > 256
          || !/^\/_next\/static\/[A-Za-z0-9_./-]+\.css$/.test(url.pathname)) throw unavailable();
      return url.pathname + url.search;
    });
    let css = '';
    for (const path of urls) {
      css += await boundedText(await check(path, 200), 'text/css');
      if (css.length > LIMIT * 4) throw unavailable();
    }
    if (requiredCssMarkers.some(marker => !css.includes(marker))) throw unavailable();
    await access(check);
    const login = await check('/login', 200);
    noStore(login);
    verifySecurityHeaders(login.headers);
    const loginHtml = await boundedText(login, 'text/html');
    if (!loginHtml.includes('Owner access')
        || !loginHtml.includes('Owner sign-in is being configured. The private dashboard remains locked.')
        || !pendingOwnerButton(loginHtml)) throw unavailable();
    await (await check('/.env', 404)).body?.cancel();
    // None of these requests contains an email or can reach the insertion branch.
    for (const [status, options] of [[405, {}], [403, {method: 'POST',
      headers: {origin: 'https://attacker.invalid'}}], [400, {method: 'POST',
      headers: {origin: base, 'content-type': 'application/json', 'sec-fetch-site': 'same-origin'},
      body: '{}'}]]) {
      const response = await check('/api/waitlist', status, options);
      noStore(response);
      await response.body?.cancel();
    }
    return {public_surface_verified: true, live_routes_contained: true,
      owner_authentication_verified: false};
  } catch {throw unavailable();}
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {console.log(JSON.stringify(await verifyContainedPublic()));}
  catch {console.error('Contained public verification failed'); process.exitCode = 1;}
}
