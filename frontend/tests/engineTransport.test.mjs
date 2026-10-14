import test from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {encode} from 'next-auth/jwt';
import {requireOwner} from '../lib/ownerAccess.ts';
import {OWNER_GITHUB_ID,PRODUCTION_ORIGIN,SESSION_SECONDS} from '../lib/ownerPolicy.ts';
import {engineDisplayReply,ENGINE_DISPLAY_PROTOCOL} from '../lib/engineTransport.ts';

const secret=randomBytes(32).toString('hex'),engineToken=randomBytes(32).toString('hex');
Object.assign(process.env,{NEXTAUTH_SECRET:secret,NEXTAUTH_URL:PRODUCTION_ORIGIN,
  GITHUB_CLIENT_ID:'fixture-client',GITHUB_CLIENT_SECRET:'fixture-secret'});
const now=Date.now(),origin='https://private-engine.example.test';
const request=(path='/api/signals?sport=nfl&view=qualified',init={})=>new Request(PRODUCTION_ORIGIN+path,init);
const ownerRequest=async(path,init={},token={})=>request(path,{...init,headers:{...init.headers,
  cookie:'__Secure-next-auth.session-token='+await encode({secret,maxAge:SESSION_SECONDS,
    token:{sub:OWNER_GITHUB_ID,ownerId:OWNER_GITHUB_ID,ownerIssuedAt:Date.now(),...token}})}});
const envelope=(patch={})=>({protocol:ENGINE_DISPLAY_PROTOCOL,resource:'signals',
  generated_at:new Date(now-1000).toISOString(),expires_at:new Date(now+10000).toISOString(),
  revision:'a'.repeat(64),data:{label:'Recorded output',raw_evidence:'never forwarded'},...patch});
const upstream=(patch={})=>Response.json(envelope(patch));
const project=value=>value && typeof value.label==='string' && value.label.length<=100 ? {label:value.label} : null;
const options=(patch={})=>({authorize:requireOwner,config:()=>({origin,token:engineToken}),
  transport:async()=>upstream(),now:()=>now,...patch});
async function unavailable(response) {
  assert.equal(response.status,503);
  assert.deepEqual(await response.json(),{error:'The evidence service is temporarily unavailable.'});
  for(const name of ['cache-control','cdn-cache-control','vercel-cdn-cache-control']) assert.equal(response.headers.get(name),'no-store');
}

test('missing, forged, expired and nonowner sessions never access config, engine or projection',async()=>{
  let calls=0;
  const blocked=options({config:()=>{calls++;throw Error('Unexpected config');},
    transport:async()=>{calls++;throw Error('Unexpected transport');}});
  const requests=[request(),request(undefined,{headers:{authorization:'Bearer '+engineToken,'x-owner-id':OWNER_GITHUB_ID}}),
    request(undefined,{headers:{cookie:'__Secure-next-auth.session-token=forged'}}),
    await ownerRequest(undefined,{}, {ownerId:'1'}),await ownerRequest(undefined,{}, {ownerIssuedAt:Date.now()-SESSION_SECONDS*1000})];
  for(const input of requests) {
    const response=await engineDisplayReply(input,'signals',()=>{calls++;return {};},blocked);
    assert.equal(response.status,401);assert.equal(response.headers.get('cache-control'),'no-store');
  }
  assert.equal(calls,0);
});

test('real owner admission sends one pinned read with only service credentials and returns projected output',async()=>{
  const input=await ownerRequest(undefined,{headers:{'x-private-release-probe':'visitor-value'}});
  let calls=0;
  const response=await engineDisplayReply(input,'signals',project,options({transport:async(url,init)=>{
    calls++;assert.equal(url.href,origin+'/v1/display/signals?sport=nfl&view=qualified');
    assert.equal(init.method,'GET');assert.equal(init.redirect,'error');assert.equal(init.cache,'no-store');
    assert.equal(init.credentials,'omit');assert.ok(init.signal instanceof AbortSignal);
    assert.deepEqual(init.headers,{Accept:'application/json',Authorization:'Bearer '+engineToken});
    return upstream();
  }}));
  assert.equal(calls,1);assert.equal(response.status,200);
  assert.deepEqual(await response.json(),{...envelope(),data:{label:'Recorded output'}});
  for(const name of ['cache-control','cdn-cache-control','vercel-cdn-cache-control']) assert.equal(response.headers.get(name),'no-store');
  assert.equal(response.headers.get('set-cookie'),null);
});

test('invalid queries, mutation, foreign resource paths and unknown resources never contact the engine',async()=>{
  let calls=0;const guarded=options({transport:async()=>{calls++;return upstream();}});
  for(const [path,init,status,resource] of [
    ['/api/signals?sport=nfl&sport=nba',{},400,'signals'],['/api/signals?upstream=https://evil.test',{},400,'signals'],
    ['/api/signals',{method:'POST'},405,'signals'],['/api/signals',{headers:{origin:'https://evil.test'}},403,'signals'],
    ['/api/signals?player=Bad%00Name',{},400,'signals'],['/api/metrics',{},400,'signals'],
    ['/api/unknown',{},404,'unknown'],['/api/scan',{},404,'scan']]) {
    assert.equal((await engineDisplayReply(await ownerRequest(path,init),resource,project,guarded)).status,status);
  }
  assert.equal(calls,0);
});

test('unset credentials, insecure or ambiguous upstream origins fail before any network read',async()=>{
  let calls=0;const input=await ownerRequest();
  const origins=[undefined,'http://engine.example.test','https://user:password@engine.example.test',
    'https://engine.example.test/path','https://engine.example.test?next=evil','https://engine.example.test#fragment',
    'https://127.0.0.1','https://[::1]','https://localhost','https://service.local','https://engine.example.test:8443'];
  for(const badOrigin of origins) await unavailable(await engineDisplayReply(input,'signals',project,options({
    config:()=>({origin:badOrigin,token:engineToken}),transport:async()=>{calls++;return upstream();}})));
  for(const token of [undefined,'short',engineToken+'\r\nInjected: value']) await unavailable(await engineDisplayReply(input,'signals',project,options({
    config:()=>({origin,token}),transport:async()=>{calls++;return upstream();}})));
  assert.equal(calls,0);
});

test('private failures, redirects and non-JSON response bodies are never reflected or retried',async()=>{
  const input=await ownerRequest();let calls=0;
  for(const response of [new Response(engineToken,{status:500}),new Response('redirect',{status:302,headers:{location:'https://evil.test'}}),
    new Response(engineToken,{headers:{'content-type':'text/html'}}),new Response('{invalid',{headers:{'content-type':'application/json'}})]) {
    await unavailable(await engineDisplayReply(input,'signals',project,options({transport:async()=>{calls++;return response;}})));
  }
  assert.equal(calls,4);
  await unavailable(await engineDisplayReply(input,'signals',project,options({transport:async()=>{throw Error(engineToken);}})));
  let forwarded=0;
  const redirected=upstream();Object.defineProperty(redirected,'redirected',{value:true});
  await unavailable(await engineDisplayReply(input,'signals',()=>{forwarded++;return {};},options({transport:async()=>redirected})));
  assert.equal(forwarded,0);
});

test('protocol, resource, revision, expiry and complete envelope keys must match before projection',async()=>{
  const input=await ownerRequest();let calls=0;
  const patches=[{protocol:'other'},{resource:'picks'},{revision:'not-a-revision'},
    {expires_at:new Date(now).toISOString()},{expires_at:new Date(now-2000).toISOString()},
    {generated_at:new Date(now+120000).toISOString()},{generated_at:'invalid'},
    {expires_at:'invalid'},{extra_private_field:engineToken},{data:undefined}];
  for(const patch of patches) await unavailable(await engineDisplayReply(input,'signals',()=>{calls++;return {};},options({transport:async()=>upstream(patch)})));
  assert.equal(calls,0);
  for(const data of [null,[],42,'string']) await unavailable(await engineDisplayReply(input,'signals',project,options({transport:async()=>Response.json(data)})));
});

test('projection is required and invalid or oversized public projections fail closed',async()=>{
  const input=await ownerRequest();
  for(const projection of [()=>null,()=>undefined,()=>{throw Error(engineToken);},()=>({bad:1n}),()=>({large:'x'.repeat(1024*1024)}),
    async()=>({label:'unawaited'}),()=>new Date(),()=>new Response('not display data'),()=>({probability:NaN})]) {
    await unavailable(await engineDisplayReply(input,'signals',projection,options()));
  }
  let getterCalled=false;const getter=Object.defineProperty({},'label',{enumerable:true,get(){getterCalled=true;return engineToken;}});
  await unavailable(await engineDisplayReply(input,'signals',()=>getter,options()));assert.equal(getterCalled,false);
  const cyclic={};cyclic.self=cyclic;
  await unavailable(await engineDisplayReply(input,'signals',()=>cyclic,options()));
});

test('even a syntactically valid projected label cannot reflect the configured service credential',async()=>{
  await unavailable(await engineDisplayReply(await ownerRequest(),'signals',project,options({
    transport:async()=>upstream({data:{label:engineToken}})})));
});

test('declared and streamed response byte limits prevent projection and cancel oversized streams',async()=>{
  const input=await ownerRequest();let projects=0,canceled=false;
  for(const length of ['1048577','-1','ambiguous']) await unavailable(await engineDisplayReply(input,'signals',()=>{projects++;return {};},options({
    transport:async()=>new Response('{}',{headers:{'content-type':'application/json','content-length':length}})})));
  const stream=new ReadableStream({start(controller){controller.enqueue(new Uint8Array(1024*1024+1));},cancel(){canceled=true;}});
  await unavailable(await engineDisplayReply(input,'signals',()=>{projects++;return {};},options({transport:async()=>new Response(stream,{headers:{'content-type':'application/json'}})})));
  assert.equal(projects,0);assert.equal(canceled,true);
});

test('caller cancellation stops pending body reads; already aborted requests never fetch',async()=>{
  const aborter=new AbortController();let calls=0,canceled=false;
  const input=await ownerRequest(undefined,{signal:aborter.signal});
  const stream=new ReadableStream({cancel(){canceled=true;}});
  const pending=engineDisplayReply(input,'signals',project,options({transport:async()=>{calls++;return new Response(stream,{headers:{'content-type':'application/json'}});}}));
  setTimeout(()=>aborter.abort(),30);
  await unavailable(await pending);assert.equal(canceled,true);assert.equal(calls,1);
  await unavailable(await engineDisplayReply(input,'signals',project,options({transport:async()=>{calls++;return upstream();}})));
  assert.equal(calls,1);
});

test('HEAD remains a validated read without a public body; upstream headers never override containment',async()=>{
  const input=await ownerRequest(undefined,{method:'HEAD'});
  const response=await engineDisplayReply(input,'signals',project,options({transport:async()=>Response.json(envelope(),{
    headers:{'cache-control':'public, max-age=10000','set-cookie':'private='+engineToken}})}));
  assert.equal(response.status,200);assert.equal(await response.text(),'');
  assert.equal(response.headers.get('cache-control'),'no-store');assert.equal(response.headers.get('set-cookie'),null);
});

test('a display envelope expiring during projection is withheld instead of being revived',async()=>{
  let clock=now;
  await unavailable(await engineDisplayReply(await ownerRequest(),'signals',value=>{
    clock=now+20000;return project(value);
  },options({now:()=>clock})));
});
