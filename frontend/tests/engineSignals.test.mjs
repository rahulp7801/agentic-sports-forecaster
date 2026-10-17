import test from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {encode} from 'next-auth/jwt';
import {engineSignalsRequest,engineSignalsReply,projectEngineSignals} from '../lib/engineSignals.ts';
import {ENGINE_DISPLAY_PROTOCOL} from '../lib/engineTransport.ts';
import {FORECAST_DISPLAY_PROTOCOL} from '../lib/forecastDisplayAuthority.ts';
import {readForecastDisplayPacket} from '../lib/forecastDisplayPacket.ts';
import {bindForecastDisplayPacket} from '../lib/forecastDisplayPacketProducer.ts';
import {forecastRequest} from '../lib/forecastPage.ts';
import {publicRequest} from '../lib/publicRequest.ts';
import {requireOwner} from '../lib/ownerAccess.ts';
import {OWNER_GITHUB_ID,PRODUCTION_ORIGIN,SESSION_SECONDS} from '../lib/ownerPolicy.ts';

const secret=randomBytes(32).toString('hex'),token=randomBytes(32).toString('hex'),now=Date.now();
Object.assign(process.env,{NEXTAUTH_SECRET:secret,NEXTAUTH_URL:PRODUCTION_ORIGIN,
  GITHUB_CLIENT_ID:'fixture-client',GITHUB_CLIENT_SECRET:'fixture-secret'});
const revision='a'.repeat(64),stamp=new Date(now-1000).toISOString();
const baseRequest={sport:'nfl',view:'library',offset:0,limit:100,revision:null,player:''};
const request=(query='?sport=nfl',init={})=>new Request(PRODUCTION_ORIGIN+'/api/signals'+query,init);
async function ownerRequest(query,init={}) {
  return request(query,{...init,headers:{...init.headers,cookie:'__Secure-next-auth.session-token='+await encode({secret,
    maxAge:SESSION_SECONDS,token:{sub:OWNER_GITHUB_ID,ownerId:OWNER_GITHUB_ID,ownerIssuedAt:Date.now()}})}});
}
const context=(query='?sport=nfl',patch={})=>Object.freeze({resource:'signals',request_url:request(query).url,method:'GET',
  generated_at:stamp,expires_at:new Date(now+10000).toISOString(),revision,signal:new AbortController().signal,...patch});
const page=(patch={})=>({search_player:'',generated_at:stamp,games:[],signals:[],
  display:{protocol:FORECAST_DISPLAY_PROTOCOL,evaluated_at:stamp,revision,view:'library',complete:true,invalid_signals:0,rows:[]},
  invalid_signals:0,total_count:0,pagination:{offset:0,next_offset:null,revision,complete:true},
  research_window:'Synthetic engine contract test',...patch});
const packet=(patch={},binding=baseRequest)=>bindForecastDisplayPacket(page(patch),binding);
const envelope=(data=packet(),patch={})=>({protocol:ENGINE_DISPLAY_PROTOCOL,resource:'signals',generated_at:stamp,
  expires_at:new Date(now+10000).toISOString(),revision,data,...patch});
const options=patch=>({authorize:requireOwner,config:()=>({origin:'https://engine.example.test',token}),
  transport:async()=>Response.json(envelope()),now:()=>now,...patch});

test('public signals grammar matches current request defaults and domain rules offline',()=>{
  const queries=['','?sport=nfl','?sport=nba&limit=1','?sport=cfb&offset=999&limit=100&revision='+revision,
    '?view=qualified','?view=candidates&sport=nfl&limit=1','?player=Jos%C3%A9%20Smith',
    '?sport=','?sport=NFL','?view=other','?offset=00','?offset=1000','?offset=-1','?limit=0','?limit=101','?limit=01',
    '?revision=','?revision='+revision.toUpperCase(),'?view=qualified&offset=1','?view=candidates&revision='+revision,
    '?player=%20Name','?player=Jose%CC%81','?player=A1','?view=qualified&player=Name',
    '?sport=nfl&sport=nba','?unknown=1','?player=Bad%00Name'];
  for(const query of queries) {
    const input=request(query);let current=null;
    try {if(publicRequest(input)===null) current=forecastRequest(new URL(input.url));} catch {}
    const actual=engineSignalsRequest(context(query));
    assert.deepEqual(actual,current,query);if(actual) assert.equal(Object.isFrozen(actual),true);
  }
  assert.equal(engineSignalsRequest(context('',{resource:'metrics'})),null);
  assert.equal(engineSignalsRequest(context('',{request_url:PRODUCTION_ORIGIN+'/api/metrics'})),null);
});

test('real owner is required even for invalid queries; canonical rejection never reads config or network',async()=>{
  let configurations=0,reads=0;
  const guarded=options({config:()=>{configurations++;throw Error(token);},transport:async()=>{reads++;throw Error(token);}});
  assert.equal((await engineSignalsReply(request('?sport=invalid'),guarded)).status,401);
  for(const query of ['?sport=invalid','?limit=0','?offset=1000','?player=%20Name','?view=qualified&player=Name']) {
    assert.equal((await engineSignalsReply(await ownerRequest(query),guarded)).status,400);
  }
  assert.deepEqual([configurations,reads],[0,0]);
});

test('prepared signals bridge verifies packet and outer revision, returning a projected envelope',async()=>{
  let reads=0;
  const original=packet();
  assert.notEqual(await readForecastDisplayPacket(original,baseRequest),null);
  const response=await engineSignalsReply(await ownerRequest(),options({transport:async()=>{reads++;return Response.json(envelope(original));}}));
  assert.equal(response.status,200);assert.equal(reads,1);
  const result=await response.json();
  assert.equal(result.revision,revision);assert.equal(result.data.pagination.revision,revision);
  assert.equal(result.data.display.revision,revision);assert.equal(Object.hasOwn(result.data,'binding'),false);
  // The prepared envelope is deliberately not the current browser's original bound packet.
  assert.equal(await readForecastDisplayPacket(result.data,baseRequest),null);
  assert.equal(response.headers.get('cache-control'),'no-store');
});

test('binding, hash, query, pagination, display and outer revision disagreement fail closed',async()=>{
  const altered=packet();altered.research_window='Hash mutation';
  for(const [value,ctx] of [[altered,context()],[packet(),context('?sport=nba')],
    [packet(),context('?sport=nfl&revision='+'b'.repeat(64))],[packet(),context(undefined,{revision:'b'.repeat(64)})],
    [packet({pagination:{offset:0,next_offset:null,revision:'b'.repeat(64),complete:true}}),context()],
    [packet({display:{...page().display,revision:'b'.repeat(64)}}),context()],
    [{...packet(),binding:undefined},context()]]) {
    assert.equal(await projectEngineSignals(value,ctx),null);
  }
});

test('packet and canonical request are snapshotted before asynchronous digest validation',async()=>{
  const value=packet(),ctx={...context()};
  const pending=projectEngineSignals(value,ctx);
  value.research_window='Changed after projection started';value.binding.request.sport='nba';
  value.pagination.revision='b'.repeat(64);
  ctx.request_url=request('?sport=nba').url;ctx.revision='b'.repeat(64);
  const result=await pending;
  assert.ok(result);assert.equal(result.research_window,'Synthetic engine contract test');
  assert.equal(result.pagination.revision,revision);
});

test('exotic, oversized or getter-bearing packet inputs never invoke getters or reach display',async()=>{
  let getters=0;const withGetter=packet();
  Object.defineProperty(withGetter,'private',{enumerable:true,get(){getters++;throw Error(token);}});
  const cyclic={};cyclic.self=cyclic;
  for(const value of [withGetter,cyclic,{large:'x'.repeat(1024*1024)},new Date(),null]) {
    assert.equal(await projectEngineSignals(value,context()),null);
  }
  assert.equal(getters,0);
});
