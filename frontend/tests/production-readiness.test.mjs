import assert from 'node:assert/strict';
import test from 'node:test';
import {livePaths,requiredCssMarkers,requiredHtmlMarkers,publicSecurityProbes,verifyProduction,verifyProductionWithRetry,verifyPublishedCaptures} from '../scripts/verify-production.mjs';
import {hosted_read_dsn} from '../scripts/verify-published-config.mjs';
const origin='https://example.test';
const html='<html><link rel="stylesheet" href="/app.css"><body><section id="waitlist">Private preview Join the waitlist</section><section id="backtest-demo">Illustrative preview Sample layout</section><a href="/login">Owner sign-in</a></body></html>';
const headers={
 'x-content-type-options':'nosniff','x-frame-options':'DENY','referrer-policy':'strict-origin-when-cross-origin',
 'cross-origin-opener-policy':'same-origin','cross-origin-resource-policy':'same-origin','x-dns-prefetch-control':'off',
 'origin-agent-cluster':'?1','x-permitted-cross-domain-policies':'none','cache-control':'no-store',
 'strict-transport-security':'max-age=63072000; includeSubDomains','permissions-policy':'camera=(), microphone=()',
 'content-security-policy':"default-src 'self'; script-src 'self' 'nonce-YWJjZA==' 'strict-dynamic'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
};
function fetcher(change=()=>null) {return async(url,options={})=>{
 const parsed=new URL(url),path=parsed.pathname+parsed.search;
 const altered=change(path,options);if(altered)return altered;
 const opts={headers};
 if(parsed.pathname==='/')return new Response(html,opts);
 if(path==='/app.css')return new Response(requiredCssMarkers.join(' '),opts);
 if(path==='/login')return new Response('Owner access',opts);
 if(parsed.pathname==='/terminal' || parsed.pathname.startsWith('/terminal/'))return new Response(null,{status:307,headers:{...headers,location:'/login'}});
 if(path==='/api/auth/csrf')return Response.json({csrfToken:'test'},opts);
 if(path==='/.env')return new Response(null,{status:404,headers});
 const probe=publicSecurityProbes.find(item=>item.path===path && (item.options?.method ?? 'GET')===(options.method ?? 'GET') && JSON.stringify(item.options?.headers ?? {})===JSON.stringify(options.headers ?? {}));
 if(probe)return Response.json({error:'Request rejected.'},{status:probe.statuses[0],headers});
 return Response.json({error:'Owner authentication required.'},{status:401,headers});
};}

test('production release requires a public demo, owner redirect and anonymous denial across every live route',async()=>{
 await verifyProduction({base:origin,fetchImpl:fetcher()});
 for(const sport of ['nfl','nba','cfb'])assert.ok(livePaths.some(path=>path.includes('sport='+sport)));
 for(const path of livePaths)await assert.rejects(verifyProduction({base:origin,fetchImpl:fetcher(target=>target===path?new Response('{}',{status:200,headers}):null)}),/unexpected HTTP 200/);
});
test('release cannot pass with a cached denial, broken owner redirect, missing login setup or stale public UI',async()=>{
 for(const marker of requiredHtmlMarkers)await assert.rejects(verifyProduction({base:origin,fetchImpl:fetcher(path=>path.startsWith('/?')?new Response(html.replace(marker,''),{headers}):null)}),/landing is stale/);
 await assert.rejects(verifyProduction({base:origin,fetchImpl:fetcher(path=>path==='/api/scans'?Response.json({error:'Owner authentication required.'},{status:401,headers:{...headers,'cache-control':'public, max-age=30'}}):null)}),/may be cached/);
 await assert.rejects(verifyProduction({base:origin,fetchImpl:fetcher(path=>path==='/terminal'?new Response(null,{status:307,headers:{...headers,location:'/open'}}):null)}),/login redirect missing/);
 await assert.rejects(verifyProduction({base:origin,fetchImpl:fetcher(path=>path==='/api/auth/csrf'?new Response('{}',{status:503,headers}):null)}),/unexpected HTTP 503/);
});
test('publication verification keeps exact source capture identity without an owner login cookie',async()=>{
 const captured_at='2026-10-06T20:00:00Z';const report={markets:{nfl:{captured_at}},schedules:{nba:{captured_at}}};
 const seen=[];await verifyPublishedCaptures(report,async key=>{seen.push(key);return {captured_at};});assert.deepEqual(seen,['markets:nfl','schedule:nba']);
 await assert.rejects(verifyPublishedCaptures(report,async()=>({captured_at:'other'})),/does not match/);
 await assert.rejects(verifyPublishedCaptures({},async()=>null),/No capture receipts/);
 await verifyProduction({base:origin,fetchImpl:fetcher(),expectedPublicReport:report,readSnapshot:async()=>({captured_at})});
});
test('release retries stay bounded and recheck the complete private boundary',async()=>{
 let homes=0;const waits=[];
 const fetchImpl=fetcher(path=>path.startsWith('/?') && ++homes===1?new Response(null,{status:503,headers}):null);
 await verifyProductionWithRetry({base:origin,fetchImpl},{attempts:2,delayMs:50,wait:async delay=>waits.push(delay),log:()=>{}});
 assert.deepEqual(waits,[50]);assert.equal(homes,2);
});
test('private receipt read preserves certificate verification and rejects duplicate TLS modes',()=>{
 const dsn='postgresql+psycopg://reader:fixture@aws-1-us-east-1.pooler.supabase.com:5432/postgres?sslmode=verify-full';
 const config=hosted_read_dsn(dsn,'fixture-ca');assert.equal(new URL(config.connectionString).port,'6543');assert.deepEqual(config.ssl,{ca:'fixture-ca',rejectUnauthorized:true});
 assert.equal(new URL(config.connectionString).searchParams.has('sslmode'),false);
 for(const value of [undefined,dsn.replace('verify-full','require'),dsn+'&sslmode=require'])assert.throws(()=>hosted_read_dsn(value));
});
