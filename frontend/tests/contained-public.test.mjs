import assert from 'node:assert/strict';
import test from 'node:test';
import {CONTAINED_ORIGIN as origin, containedPaths, verifyContainedAccess,
  verifyContainedPublic} from '../scripts/verify-contained-public.mjs';
import {requiredHtmlMarkers, requiredCssMarkers} from '../scripts/verify-production.mjs';

const security = {
  'x-content-type-options':'nosniff', 'x-frame-options':'DENY',
  'referrer-policy':'strict-origin-when-cross-origin', 'cross-origin-opener-policy':'same-origin',
  'cross-origin-resource-policy':'same-origin', 'x-dns-prefetch-control':'off',
  'origin-agent-cluster':'?1', 'x-permitted-cross-domain-policies':'none',
  'strict-transport-security':'max-age=63072000; includeSubDomains', 'permissions-policy':'camera=()',
  'content-security-policy':"default-src 'self'; script-src 'self' 'nonce-aGVsbG8=' 'strict-dynamic'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; connect-src 'self'",
};
const html = requiredHtmlMarkers.join(' ') + '<link href="/_next/static/chunks/main.css" rel="stylesheet">';
const login = '<h1>Owner access</h1><button disabled="">Continue with GitHub</button><p>Owner sign-in is being configured. The private dashboard remains locked.</p>';
function fixture(change = () => undefined) {
  const calls = [];
  const fetchImpl = async (address, options) => {
    const url = new URL(address);
    calls.push({url, options});
    assert.equal(url.origin, origin);
    assert.equal(options.redirect, 'manual');
    assert.equal(options.credentials, 'omit');
    assert.equal(options.cache, 'no-store');
    assert.ok(options.signal instanceof AbortSignal);
    assert.equal(options.headers?.authorization, undefined);
    const custom = change(url, options);
    if (custom) return custom;
    if (url.pathname === '/') return new Response(html, {headers:{...security,'content-type':'text/html'}});
    if (url.pathname.endsWith('.css')) return new Response(requiredCssMarkers.join(''), {headers:{'content-type':'text/css'}});
    if (url.pathname === '/login') return new Response(login, {headers:{...security,'cache-control':'no-store','content-type':'text/html'}});
    if (url.pathname === '/.env') return new Response('', {status:404});
    let status = 403;
    if (url.pathname === '/api/waitlist') status = options.method !== 'POST' ? 405 : options.body === '{}' ? 400 : 403;
    return new Response('', {status,headers:{'cache-control':'no-store'}});
  };
  return {calls, fetchImpl};
}
const rejected = promise => assert.rejects(promise, error => error.message === 'Contained public verification failed');

test('public-only success explicitly does not prove owner authentication', async () => {
  const {fetchImpl, calls} = fixture();
  assert.deepEqual(await verifyContainedPublic({fetchImpl}), {public_surface_verified:true,
    live_routes_contained:true,owner_authentication_verified:false});
  assert.ok(containedPaths.every(path => calls.some(call => call.url.href === origin + path)));
  assert.ok(!calls.some(call => call.url.pathname.startsWith('/api/auth/')));
  const posts = calls.filter(call => call.options.method === 'POST');
  assert.equal(posts.length, 3);
  assert.equal(posts.filter(call => call.options.body).length, 1);
  assert.equal(posts.find(call => call.options.body).options.body, '{}');
  assert.ok(!JSON.stringify(posts).includes('@'));
});

test('preflight perimeter checks work before a fresh public landing is deployed', async () => {
  const {fetchImpl, calls} = fixture(url => {assert.notEqual(url.pathname, '/');});
  assert.deepEqual(await verifyContainedAccess({fetchImpl}), {live_routes_contained:true,owner_authentication_verified:false});
  assert.equal(calls.length, containedPaths.length + 1);
});

test('the actual WAF private no-store max-age zero header remains valid', async () => {
  const {fetchImpl} = fixture(() => new Response('', {status:403,
    headers:{'cache-control':'private, no-store, max-age=0'}}));
  await verifyContainedAccess({fetchImpl});
});

test('all noncanonical origins are rejected before any request', async () => {
  for (const base of ['https://attacker.invalid',origin+'/',origin+'/terminal','http://'+new URL(origin).hostname]) {
    const {fetchImpl,calls} = fixture();
    await rejected(verifyContainedPublic({base,fetchImpl}));
    await rejected(verifyContainedAccess({base,fetchImpl}));
    assert.equal(calls.length,0);
  }
});

test('each protected path fails closed for app auth, redirects or public output', async () => {
  for (const path of containedPaths) for (const status of [200,401,307]) {
    const {fetchImpl} = fixture(url => url.href === origin+path ? new Response('',{status,headers:{'cache-control':'no-store'}}) : undefined);
    await rejected(verifyContainedAccess({fetchImpl}));
  }
});

test('protected and waitlist responses cannot be cacheable', async () => {
  for (const cache of ['', 'public, no-store', 'no-store, max-age=60', 'no-store, s-maxage=60', 'x-no-store']) {
    await rejected(verifyContainedAccess({fetchImpl:fixture(url => url.pathname==='/api/signals'
      ? new Response('',{status:403,headers:{'cache-control':cache}}) : undefined).fetchImpl}));
  }
  for (const name of ['cdn-cache-control','vercel-cdn-cache-control']) {
    await rejected(verifyContainedAccess({fetchImpl:fixture(url => url.pathname==='/api/signals'
      ? new Response('',{status:403,headers:{'cache-control':'no-store',[name]:'public'}}) : undefined).fetchImpl}));
  }
  await rejected(verifyContainedPublic({fetchImpl:fixture(url => url.pathname==='/api/waitlist'
    ? new Response('',{status:405}) : undefined).fetchImpl}));
});

test('stale landing, styles and enabled owner login are rejected', async () => {
  for (const [path,body,type] of [['/','Old landing','text/html'],['/_next/static/chunks/main.css','old','text/css'],
    ['/login','<h1>Owner access</h1><button>Continue</button>','text/html']]) {
    await rejected(verifyContainedPublic({fetchImpl:fixture(url => url.pathname===path
      ? new Response(body,{headers:{...security,'cache-control':'no-store','content-type':type}}) : undefined).fetchImpl}));
  }
});

test('only the actual disabled attribute on the GitHub owner button proves pending access', async () => {
  for (const button of ['<button aria-disabled="true">Continue with GitHub</button>',
    '<button data-disabled="">Continue with GitHub</button>',
    '<button title=" disabled ">Continue with GitHub</button>',
    '<button>Continue with GitHub</button><button disabled>Unrelated</button>']) {
    const body = '<h1>Owner access</h1>'+button+'Owner sign-in is being configured. The private dashboard remains locked.';
    await rejected(verifyContainedPublic({fetchImpl:fixture(url=>url.pathname==='/login'
      ? new Response(body,{headers:{...security,'cache-control':'no-store','content-type':'text/html'}}) : undefined).fetchImpl}));
  }
});

test('HTML and CSS require the exact media type, allowing charset parameters', async () => {
  for (const [path,body,type] of [['/',html,'text/html-invalid'],
    ['/_next/static/chunks/main.css',requiredCssMarkers.join(''),'text/css-invalid']]) {
    await rejected(verifyContainedPublic({fetchImpl:fixture(url=>url.pathname===path
      ? new Response(body,{headers:{...security,'content-type':type}}) : undefined).fetchImpl}));
  }
  await verifyContainedPublic({fetchImpl:fixture(url=>url.pathname.endsWith('.css')
    ? new Response(requiredCssMarkers.join(''),{headers:{'content-type':'Text/CSS; charset=utf-8'}}) : undefined).fetchImpl});
});

test('stylesheet injection cannot send probes to external or arbitrary paths', async () => {
  for (const style of ['https://attacker.invalid/main.css','//attacker.invalid/main.css','/api/private.css','/login.css']) {
    const {fetchImpl,calls} = fixture(url => url.pathname==='/' ? new Response(requiredHtmlMarkers.join(' ')+`<link href="${style}">`,
      {headers:{...security,'content-type':'text/html'}}) : undefined);
    await rejected(verifyContainedPublic({fetchImpl}));
    assert.equal(calls.length,1);
  }
});

test('oversized, excessive or invalid stylesheet and HTML bodies fail closed', async () => {
  for (const body of ['x'.repeat(1024*1024+1),requiredHtmlMarkers.join(' ')+Array.from({length:13},(_,i)=>`<link href="/_next/static/${i}.css">`).join('')]) {
    await rejected(verifyContainedPublic({fetchImpl:fixture(url => url.pathname==='/'
      ? new Response(body,{headers:{...security,'content-type':'text/html'}}) : undefined).fetchImpl}));
  }
  await rejected(verifyContainedPublic({fetchImpl:fixture(url=>url.pathname.endsWith('.css')
    ? new Response('x'.repeat(1024*1024+1),{headers:{'content-type':'text/css'}}) : undefined).fetchImpl}));
});

test('network and security failures never echo provider or response payloads', async () => {
  await rejected(verifyContainedPublic({fetchImpl:async()=>{throw Error('sensitive-provider-text');}}));
  await rejected(verifyContainedPublic({fetchImpl:fixture(url=>url.pathname==='/'
    ? new Response(html,{headers:{'content-type':'text/html'}}) : undefined).fetchImpl}));
});
